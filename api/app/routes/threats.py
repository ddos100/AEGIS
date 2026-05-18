"""Threat catalogue endpoints (Phase 7.1).

Every route in this router is gated by `requires_module("AEGIS-THREAT")`
— tenants without the SKU receive 402 Payment Required with a structured
{module, action, contact} payload.

Phase 7.1 ships READ-ONLY browse over the global threat catalogue. The
exposure engine (`/v1/exposures`) and mitigation orchestrator
(`/v1/mitigations`) land in Phase 7.3 / 7.4.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, func

from app.core.deps import CurrentUser, DBSession
from app.core.licence import (
    list_active_modules,
    requires_module,
)
from app.models.threat import Threat
from app.schemas.threats import (
    ModuleInfo,
    ThreatBrief,
    ThreatDetail,
    ThreatListResponse,
)

router = APIRouter(
    prefix="/threats",
    tags=["threats"],
    dependencies=[Depends(requires_module("AEGIS-THREAT"))],
)


# ---------- /v1/licence (not gated — anyone can read their own entitlements) -

licence_router = APIRouter(prefix="/licence", tags=["licence"])


@licence_router.get("", response_model=list[ModuleInfo])
async def list_licence(db: DBSession, user: CurrentUser) -> list[ModuleInfo]:
    active = await list_active_modules(db, user.tenant_id)
    return [
        ModuleInfo(
            module_sku=m.module_sku,
            edition=m.edition,
            valid_to=m.valid_to,
            feature_flags=m.feature_flags,
            limits=m.limits,
        )
        for m in active
    ]


# ---------- /v1/threats -----------------------------------------------------

@router.get("", response_model=ThreatListResponse)
async def list_threats(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    q:        Annotated[str | None, Query(description="Substring match on threat_id/title/source_ref")] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    vector:   Annotated[str | None, Query()] = None,
    threat_class: Annotated[str | None, Query(alias="class")] = None,
    sector:   Annotated[str | None, Query()] = None,
    page:     Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ThreatListResponse:
    stmt = select(Threat)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Threat.threat_id.ilike(like),
            Threat.title.ilike(like),
            Threat.source_ref.ilike(like),
        ))
    if severity:
        stmt = stmt.where(Threat.severity.in_(severity))
    if vector:
        stmt = stmt.where(Threat.vectors.any(vector))
    if threat_class:
        stmt = stmt.where(Threat.classes.any(threat_class))
    if sector:
        stmt = stmt.where(Threat.sector_amplifiers.any(sector))

    # total before pagination
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    rows = (await db.execute(
        stmt.order_by(Threat.severity, Threat.threat_id)
            .offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    pages = max(1, (total + per_page - 1) // per_page)
    return ThreatListResponse(
        items=[ThreatBrief.model_validate(r) for r in rows],
        total=total, page=page, pages=pages, per_page=per_page,
    )


@router.get("/{threat_id}", response_model=ThreatDetail)
async def get_threat(threat_id: str, db: DBSession, user: CurrentUser) -> ThreatDetail:  # noqa: ARG001
    row = (await db.execute(
        select(Threat).where(Threat.threat_id == threat_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Threat not found")
    return ThreatDetail.model_validate(row)


@router.get("/_/stats", response_model=dict)
async def threats_stats(db: DBSession, user: CurrentUser) -> dict:  # noqa: ARG001
    """Lightweight aggregate for the dashboard tile."""
    rows = (await db.execute(
        select(Threat.severity, func.count(Threat.id)).group_by(Threat.severity)
    )).all()
    by_sev = {sev: int(n) for sev, n in rows}
    total = sum(by_sev.values())
    return {
        "total": total,
        "by_severity": by_sev,
    }
