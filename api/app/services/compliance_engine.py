"""Compliance engine — auto-assess controls against the current state of
the AI System Registry.

Strategy: the engine NEVER auto-marks a control as ``implemented``.
Implementation is a human attestation. The engine only marks:

  - ``partial``          when the auto_check predicates are satisfied for
                         a given system,
  - ``not_implemented``  when the predicates are NOT satisfied AND the
                         control is mandatory,
  - ``not_assessed``     when there is no human attestation + no predicate.

Predicate keys supported (all optional; each is evaluated independently
and combined with AND inside a single auto_check map):

  registry_completeness_min      int     system.completeness_score >= value
  aisia_status_in                list    system.aisia_status in list
  aisia_treatment_decided        bool    AISIA.treatment_decision is not null
  data_types_documented          bool    system.data_types_processed non-empty
  intended_purpose_documented    bool    system.intended_purpose non-empty
  human_oversight_documented     bool    system.human_oversight_desc non-empty
  owner_assigned                 bool    system.owner_user_id is not null
  risk_assessed                  bool    system.current_risk_score is not null
  usage_monitored                bool    system has at least one ai_usage_event
  eu_ai_act_category_documented  bool    system.eu_ai_act_category is not null
  eu_ai_act_category_not         str     system.eu_ai_act_category != value
  provider_assessed              bool    catalogue trust_score is not null
                                         OR provider_name_freetext populated
  provider_jurisdiction_permitted bool   AIProvider.hq_country in permitted list

These mirror the auto_check fields in catalogue/compliance-frameworks/*.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ai_provider import AIProvider
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent
from app.models.aisia_record import AISIARecord
from app.models.compliance_control import ComplianceControl
from app.models.compliance_framework import ComplianceFramework
from app.models.compliance_mapping import ComplianceMapping

# Default list of "permitted" jurisdictions for cross-border data transfer
# auto-checks. Operators may override per-tenant later; this is a sane
# DPDPA-aligned baseline.
DEFAULT_PERMITTED_JURISDICTIONS = {"IN", "EU", "US", "GB", "JP", "SG", "AU", "CA"}


@dataclass(slots=True)
class FrameworkScore:
    framework_id: UUID
    slug: str
    name: str
    total_controls: int
    by_status: dict[str, int]
    score_pct: float           # weighted: implemented + 0.5 * partial
    gaps: list[dict[str, Any]]


def _system_dict(s: AISystem) -> dict[str, Any]:
    return {
        "id": s.id,
        "completeness_score":   s.completeness_score or 0,
        "aisia_status":         s.aisia_status,
        "data_types_processed": list(s.data_types_processed or []),
        "intended_purpose":     s.intended_purpose,
        "human_oversight_desc": s.human_oversight_desc,
        "owner_user_id":        s.owner_user_id,
        "current_risk_score":   s.current_risk_score,
        "eu_ai_act_category":   s.eu_ai_act_category,
        "provider_name_freetext": s.provider_name_freetext,
        "catalogue_service_id": s.catalogue_service_id,
        "provider_id":          s.provider_id,
    }


async def _enrich_system_context(session, sys_d: dict) -> dict:
    """Pull a couple of extra facts needed by some predicates."""
    if sys_d["catalogue_service_id"]:
        catalogue = (await session.execute(
            select(AIService).where(AIService.id == sys_d["catalogue_service_id"])
        )).scalar_one_or_none()
        if catalogue:
            sys_d["catalogue_risk_hints"] = catalogue.risk_hints or {}
    aisia = (await session.execute(
        select(AISIARecord).where(AISIARecord.ai_system_id == sys_d["id"])
    )).scalar_one_or_none()
    sys_d["aisia_treatment_decision"] = aisia.treatment_decision if aisia else None

    provider_country = None
    if sys_d["provider_id"]:
        country = (await session.execute(
            select(AIProvider.hq_country).where(AIProvider.id == sys_d["provider_id"])
        )).scalar_one_or_none()
        provider_country = country
    sys_d["provider_country"] = provider_country

    # Usage observed?
    usage = (await session.execute(
        select(func.count(AIUsageEvent.id)).where(AIUsageEvent.ai_system_id == sys_d["id"])
    )).scalar_one()
    sys_d["usage_count"] = usage or 0
    return sys_d


def evaluate_auto_check(check: dict[str, Any], sys_d: dict) -> bool:
    """Return True if every predicate in the auto_check map is satisfied."""
    if not check:
        return False  # No predicates → can't auto-mark partial

    for k, v in check.items():
        if k == "registry_completeness_min":
            if (sys_d.get("completeness_score") or 0) < int(v): return False
        elif k == "aisia_status_in":
            if sys_d.get("aisia_status") not in v: return False
        elif k == "aisia_treatment_decided":
            if bool(v) != (sys_d.get("aisia_treatment_decision") is not None): return False
        elif k == "data_types_documented":
            populated = bool(sys_d.get("data_types_processed"))
            if bool(v) != populated: return False
        elif k == "intended_purpose_documented":
            populated = bool((sys_d.get("intended_purpose") or "").strip())
            if bool(v) != populated: return False
        elif k == "human_oversight_documented":
            populated = bool((sys_d.get("human_oversight_desc") or "").strip())
            if bool(v) != populated: return False
        elif k == "owner_assigned":
            populated = sys_d.get("owner_user_id") is not None
            if bool(v) != populated: return False
        elif k == "risk_assessed":
            populated = sys_d.get("current_risk_score") is not None
            if bool(v) != populated: return False
        elif k == "usage_monitored":
            ok = (sys_d.get("usage_count") or 0) > 0
            if bool(v) != ok: return False
        elif k == "eu_ai_act_category_documented":
            populated = bool(sys_d.get("eu_ai_act_category"))
            if bool(v) != populated: return False
        elif k == "eu_ai_act_category_not":
            if sys_d.get("eu_ai_act_category") == v: return False
        elif k == "provider_assessed":
            ok = (sys_d.get("provider_id") is not None
                  or bool((sys_d.get("provider_name_freetext") or "").strip()))
            if bool(v) != ok: return False
        elif k == "provider_jurisdiction_permitted":
            ok = (sys_d.get("provider_country") or "").upper() in DEFAULT_PERMITTED_JURISDICTIONS
            # Unknown country = not-permitted (conservative)
            if bool(v) != ok: return False
        # Unknown predicate → ignored (forward-compat)
    return True


async def auto_assess(*, session, tenant_id: UUID, framework_slug: str) -> dict[str, Any]:
    """Run auto-assessment across all systems for a framework.

    Strategy: for every (control, system) pair, evaluate the auto_check
    predicate; upsert a compliance_mapping row. Existing mappings with a
    human attestation (status='implemented') are never overwritten.
    """
    framework = (await session.execute(
        select(ComplianceFramework).where(ComplianceFramework.slug == framework_slug)
    )).scalar_one_or_none()
    if framework is None:
        return {"ok": False, "error": f"framework {framework_slug!r} not found"}

    controls = (await session.execute(
        select(ComplianceControl).where(ComplianceControl.framework_id == framework.id)
    )).scalars().all()
    systems = (await session.execute(select(AISystem))).scalars().all()

    if not systems:
        return {"ok": True, "framework": framework_slug, "controls": len(controls),
                "systems": 0, "assessed": 0}

    # Pre-enrich each system once.
    enriched = []
    for s in systems:
        d = _system_dict(s)
        await _enrich_system_context(session, d)
        enriched.append(d)

    assessed = 0
    for ctrl in controls:
        for sys_d in enriched:
            # Don't overwrite a human attestation.
            existing = (await session.execute(
                select(ComplianceMapping)
                .where((ComplianceMapping.tenant_id == tenant_id) &
                       (ComplianceMapping.control_id == ctrl.id) &
                       (ComplianceMapping.ai_system_id == sys_d["id"]))
            )).scalar_one_or_none()
            if existing is not None and existing.status == "implemented":
                continue

            satisfies = evaluate_auto_check(ctrl.auto_check or {}, sys_d)
            new_status = "partial" if satisfies else (
                "not_implemented" if ctrl.is_mandatory and ctrl.auto_check else "not_assessed"
            )

            stmt = (
                pg_insert(ComplianceMapping)
                .values(
                    tenant_id=tenant_id,
                    control_id=ctrl.id,
                    ai_system_id=sys_d["id"],
                    status=new_status,
                    implementation_notes="Auto-assessed by AEGIS compliance engine"
                                          + (f" — auto_check satisfied" if satisfies else ""),
                    last_assessed_at=func.now(),
                )
                .on_conflict_do_update(
                    constraint="uq_mappings_unique",
                    set_={
                        "status": new_status,
                        "implementation_notes": "Auto-assessed by AEGIS compliance engine"
                                                  + (f" — auto_check satisfied" if satisfies else ""),
                        "last_assessed_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            assessed += 1

    return {
        "ok": True, "framework": framework_slug,
        "controls": len(controls), "systems": len(systems), "assessed": assessed,
    }


async def framework_score(*, session, framework_slug: str) -> FrameworkScore | None:
    """Compute a compliance % score for a framework across the active tenant."""
    framework = (await session.execute(
        select(ComplianceFramework).where(ComplianceFramework.slug == framework_slug)
    )).scalar_one_or_none()
    if framework is None:
        return None
    controls = (await session.execute(
        select(ComplianceControl).where(ComplianceControl.framework_id == framework.id)
    )).scalars().all()
    mappings = (await session.execute(
        select(ComplianceMapping.control_id, ComplianceMapping.status)
        .join(ComplianceControl, ComplianceMapping.control_id == ComplianceControl.id)
        .where(ComplianceControl.framework_id == framework.id)
    )).all()

    by_status = {"implemented": 0, "partial": 0, "not_implemented": 0,
                 "not_applicable": 0, "not_assessed": 0}
    # Reduce to one status per control (best status wins: implemented > partial > not_*).
    best_per_control: dict[UUID, str] = {}
    rank = {"implemented": 5, "partial": 4, "not_applicable": 3,
            "not_assessed": 2, "not_implemented": 1}
    for cid, status in mappings:
        if cid not in best_per_control or rank[status] > rank[best_per_control[cid]]:
            best_per_control[cid] = status

    for cid in (c.id for c in controls):
        s = best_per_control.get(cid, "not_assessed")
        by_status[s] = by_status.get(s, 0) + 1

    total = len(controls) or 1
    score = (by_status["implemented"] + 0.5 * by_status["partial"]) / total * 100

    gaps = [
        {"control_id": c.control_id, "title": c.title, "category": c.category,
         "status": best_per_control.get(c.id, "not_assessed")}
        for c in controls
        if best_per_control.get(c.id, "not_assessed") in ("not_implemented", "not_assessed")
    ]

    return FrameworkScore(
        framework_id=framework.id, slug=framework.slug, name=framework.name,
        total_controls=len(controls), by_status=by_status,
        score_pct=round(score, 1), gaps=gaps,
    )
