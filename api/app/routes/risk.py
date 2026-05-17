"""Risk Assessment endpoints (Phase 4).

  GET  /v1/risk/systems/{id}/assessment    Latest assessment + history
  POST /v1/risk/systems/{id}/assess        Re-score now (analyst+)
  GET  /v1/risk/systems/{id}/narrative     Claude narrative (Critical/High)
  GET  /v1/risk/summary                    Tenant-wide risk posture
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select

from app.core.deps import CurrentUser, DBSession, require_analyst
from app.integrations.claude.client import generate_risk_narrative
from app.models.ai_provider import AIProvider
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.risk_assessment import RiskAssessment
from app.schemas.risk_policy import RiskAssessmentRow, RiskSummary
from app.services.risk_engine import compute_risk_score

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/summary", response_model=RiskSummary)
async def risk_summary(db: DBSession, user: CurrentUser):  # noqa: ARG001
    total = (await db.execute(select(func.count(AISystem.id)))).scalar_one()
    by_level: dict[str, int] = dict(
        ((lvl, n) for lvl, n in (await db.execute(
            select(AISystem.risk_level, func.count(AISystem.id))
            .group_by(AISystem.risk_level)
        )).all())
    )
    avg = (await db.execute(
        select(func.avg(AISystem.current_risk_score))
    )).scalar_one() or 0
    # Top three contributing drivers across the most recent assessments.
    drivers_sql = (await db.execute(
        select(
            func.avg(RiskAssessment.data_sensitivity_score).label("data_sensitivity"),
            func.avg(RiskAssessment.ai_capability_score).label("ai_capability"),
            func.avg(RiskAssessment.regulatory_exposure_score).label("regulatory_exposure"),
            func.avg(RiskAssessment.access_scope_score).label("access_scope"),
            func.avg(RiskAssessment.provider_trust_score).label("provider_trust"),
        )
    )).first()
    drivers = []
    if drivers_sql:
        for name in ("data_sensitivity", "ai_capability", "regulatory_exposure",
                     "access_scope", "provider_trust"):
            v = getattr(drivers_sql, name, None) or 0
            drivers.append({"name": name, "avg": round(float(v), 1)})
        drivers.sort(key=lambda d: d["avg"], reverse=True)
        drivers = drivers[:3]
    return RiskSummary(
        total_systems=total,
        by_level=by_level,
        avg_score=round(float(avg), 1),
        top_drivers=drivers,
    )


@router.get("/systems/{system_id}/assessment", response_model=list[RiskAssessmentRow])
async def system_history(
    system_id: UUID,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    rows = (await db.execute(
        select(RiskAssessment)
        .where(RiskAssessment.ai_system_id == system_id)
        .order_by(desc(RiskAssessment.calculated_at))
        .limit(limit)
    )).scalars().all()
    return [RiskAssessmentRow.model_validate(r) for r in rows]


@router.post("/recalculate-all")
async def recalculate_all(
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> dict:
    """Score every AI system in the current tenant synchronously.

    Designed for the "Risk posture is blank" path: a fresh tenant has no
    scored systems, so the dashboard average is 0 / null. Hitting this
    endpoint walks the Registry, computes the 5-dimension score per
    system, writes a RiskAssessment history row, and mirrors the score
    onto the registry row — same code path as POST /systems/{id}/assess,
    but applied to every system at once. Claude narratives are skipped
    here to keep the response fast; the daily Celery beat picks them up
    for Critical / High systems.
    """
    systems = (await db.execute(select(AISystem))).scalars().all()
    if not systems:
        return {"ok": True, "scored": 0, "skipped": 0, "tenant_empty": True}

    scored = 0
    skipped = 0
    for system in systems:
        catalogue = None
        if system.catalogue_service_id:
            cat_row = (await db.execute(
                select(AIService).where(AIService.id == system.catalogue_service_id)
            )).scalar_one_or_none()
            if cat_row is not None:
                catalogue = {
                    "capabilities":   cat_row.capabilities,
                    "risk_hints":     cat_row.risk_hints,
                    "provider_id":    cat_row.provider_id,
                }

        try:
            score = compute_risk_score(_system_dict(system), catalogue=catalogue)
        except Exception:  # noqa: BLE001 — keep going on individual failures
            skipped += 1
            continue

        row = RiskAssessment(
            tenant_id=user.tenant_id,
            ai_system_id=system.id,
            data_sensitivity_score=score.data_sensitivity,
            ai_capability_score=score.ai_capability,
            regulatory_exposure_score=score.regulatory_exposure,
            access_scope_score=score.access_scope,
            provider_trust_score=score.provider_trust,
            total_score=score.total,
            risk_level=score.risk_level,
            scoring_inputs=score.inputs,
            ai_narrative=None,
            calculated_by="manual-bulk",
            calculated_at=datetime.now(timezone.utc),
        )
        db.add(row)
        system.current_risk_score    = score.total
        system.last_risk_assessed_at = row.calculated_at
        scored += 1

    await db.flush()
    return {"ok": True, "scored": scored, "skipped": skipped, "total": len(systems)}


@router.post("/systems/{system_id}/assess", response_model=RiskAssessmentRow)
async def reassess(
    system_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> RiskAssessmentRow:
    """Manual re-score. Always uses the current Claude narrative cache (skip)."""
    system = (await db.execute(
        select(AISystem).where(AISystem.id == system_id)
    )).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="AI system not found")

    catalogue = None
    if system.catalogue_service_id:
        cat_row = (await db.execute(
            select(AIService).where(AIService.id == system.catalogue_service_id)
        )).scalar_one_or_none()
        if cat_row is not None:
            catalogue = {
                "capabilities":   cat_row.capabilities,
                "risk_hints":     cat_row.risk_hints,
                "provider_id":    cat_row.provider_id,
            }

    score = compute_risk_score(_system_dict(system), catalogue=catalogue)

    narrative = None
    if score.risk_level in ("critical", "high"):
        narrative = await generate_risk_narrative(_system_dict(system), {
            "data_sensitivity":    score.data_sensitivity,
            "ai_capability":       score.ai_capability,
            "regulatory_exposure": score.regulatory_exposure,
            "access_scope":        score.access_scope,
            "provider_trust":      score.provider_trust,
            "total":               score.total,
            "risk_level":          score.risk_level,
        })

    row = RiskAssessment(
        tenant_id=system.tenant_id,
        ai_system_id=system.id,
        data_sensitivity_score=score.data_sensitivity,
        ai_capability_score=score.ai_capability,
        regulatory_exposure_score=score.regulatory_exposure,
        access_scope_score=score.access_scope,
        provider_trust_score=score.provider_trust,
        total_score=score.total,
        risk_level=score.risk_level,
        scoring_inputs=score.inputs,
        ai_narrative=narrative,
        ai_model_used="claude-sonnet-4-6" if narrative else None,
        calculated_by="manual",
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(row)

    # Mirror the latest score onto the registry row so the Registry UI is fresh.
    system.current_risk_score    = score.total
    system.last_risk_assessed_at = row.calculated_at
    await db.flush()
    await db.refresh(row)
    return RiskAssessmentRow.model_validate(row)


def _system_dict(system: AISystem) -> dict:
    return {
        "name":                   system.name,
        "category":               system.category,
        "subcategory":            system.subcategory,
        "intended_purpose":       system.intended_purpose,
        "data_types_processed":   list(system.data_types_processed or []),
        "affected_data_subjects": list(system.affected_data_subjects or []),
        "user_population":        system.user_population,
        "eu_ai_act_category":     system.eu_ai_act_category,
        "geographic_scope":       list(system.geographic_scope or []),
        "compliance_flags":       dict(system.compliance_flags or {}),
        "risk_level":             system.risk_level,
        "current_risk_score":     system.current_risk_score,
        "human_oversight_desc":   system.human_oversight_desc,
        "output_type":            system.output_type,
    }
