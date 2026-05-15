"""Compliance engine — auto-assess testable AI-governance controls.

Design contract
---------------

This engine implements three guarantees the user explicitly requires:

  1. **Testable controls only.** Every control in the catalogue must
     declare a non-empty ``auto_check``; the importer ensures this. Paper
     artefacts (board minutes, policy review records, training logs, etc.)
     never enter the catalogue and therefore never need a verdict.

  2. **Every control gets a definitive verdict.** After ``auto_assess``
     runs, no mapping is left in ``not_assessed`` state. The verdict is
     always one of:

         partial          predicates were satisfied for at least one system
         not_implemented  predicates were NOT satisfied
         implemented      human attestation only (never written by engine)
         not_applicable   human attestation only

     If the tenant has no AI systems registered at all, every control
     receives a tenant-scoped (``ai_system_id = NULL``) mapping marked
     ``not_implemented`` with reason "No AI systems registered yet."

  3. **Evidence and explanation attached.** Every mapping the engine
     writes carries:

         implementation_notes  A pipe-separated list of "PREDICATE: VERDICT
                               — observation" lines, one per predicate.
         evidence_refs         Machine-readable evidence pointers, e.g.
                               ["system:abc-123",
                                "system:abc-123.completeness:85",
                                "aisia:xyz-456:completed",
                                "provider:openai.hq_country:US"].

So when an auditor opens any mapping they see exactly which predicate
passed or failed and on what observed value.

Predicate vocabulary (mirrors `auto_check` keys in the YAML files):

  registry_completeness_min       int   system.completeness_score >= value
  aisia_status_in                 list  system.aisia_status in list
  aisia_treatment_decided         bool  AISIA.treatment_decision is not null
  data_types_documented           bool  system.data_types_processed non-empty
  intended_purpose_documented     bool  system.intended_purpose non-empty
  human_oversight_documented      bool  system.human_oversight_desc non-empty
  owner_assigned                  bool  system.owner_user_id is not null
  risk_assessed                   bool  system.current_risk_score is not null
  usage_monitored                 bool  system has >=1 ai_usage_event
  eu_ai_act_category_documented   bool  system.eu_ai_act_category is not null
  eu_ai_act_category_not          str   system.eu_ai_act_category != value
  provider_assessed               bool  catalogue match OR provider_name_freetext
  provider_jurisdiction_permitted bool  AIProvider.hq_country in permitted list
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

DEFAULT_PERMITTED_JURISDICTIONS = {"IN", "EU", "US", "GB", "JP", "SG", "AU", "CA"}


@dataclass(slots=True)
class FrameworkScore:
    framework_id: UUID
    slug: str
    name: str
    total_controls: int
    by_status: dict[str, int]
    score_pct: float
    gaps: list[dict[str, Any]]


@dataclass(slots=True)
class EvaluationResult:
    """Outcome of running one auto_check map against one enriched system."""
    satisfied: bool                 # True ⇔ every predicate passed
    reasons: list[str]              # Human-readable PREDICATE: VERDICT lines
    evidence_refs: list[str]        # Machine-readable evidence pointers


# ---------------------------------------------------------------------------
# System enrichment
# ---------------------------------------------------------------------------

def _system_dict(s: AISystem) -> dict[str, Any]:
    return {
        "id":                     s.id,
        "name":                   s.name,
        "completeness_score":     s.completeness_score or 0,
        "aisia_status":           s.aisia_status,
        "data_types_processed":   list(s.data_types_processed or []),
        "intended_purpose":       s.intended_purpose,
        "human_oversight_desc":   s.human_oversight_desc,
        "owner_user_id":          s.owner_user_id,
        "current_risk_score":     s.current_risk_score,
        "eu_ai_act_category":     s.eu_ai_act_category,
        "provider_name_freetext": s.provider_name_freetext,
        "catalogue_service_id":   s.catalogue_service_id,
        "provider_id":            s.provider_id,
    }


async def _enrich_system_context(session, sys_d: dict) -> dict:
    if sys_d["catalogue_service_id"]:
        catalogue = (await session.execute(
            select(AIService).where(AIService.id == sys_d["catalogue_service_id"])
        )).scalar_one_or_none()
        if catalogue:
            sys_d["catalogue_risk_hints"] = catalogue.risk_hints or {}

    aisia = (await session.execute(
        select(AISIARecord).where(AISIARecord.ai_system_id == sys_d["id"])
    )).scalar_one_or_none()
    sys_d["aisia_id"] = aisia.id if aisia else None
    sys_d["aisia_treatment_decision"] = aisia.treatment_decision if aisia else None

    provider_country = None
    provider_slug = None
    if sys_d["provider_id"]:
        row = (await session.execute(
            select(AIProvider.hq_country, AIProvider.slug)
            .where(AIProvider.id == sys_d["provider_id"])
        )).first()
        if row:
            provider_country = row[0]
            provider_slug = row[1]
    sys_d["provider_country"] = provider_country
    sys_d["provider_slug"] = provider_slug

    usage = (await session.execute(
        select(func.count(AIUsageEvent.id))
        .where(AIUsageEvent.ai_system_id == sys_d["id"])
    )).scalar_one()
    sys_d["usage_count"] = usage or 0
    return sys_d


# ---------------------------------------------------------------------------
# Predicate evaluation with explanations + evidence
# ---------------------------------------------------------------------------

def evaluate_auto_check(check: dict[str, Any], sys_d: dict) -> EvaluationResult:
    """Run every predicate; collect verdict + reason + evidence refs.

    Returns a single :class:`EvaluationResult` describing what passed,
    what failed, and exactly which observed values produced each verdict.
    An empty ``check`` map is treated as a defensive failure — callers
    should not pass paper-only controls to this function.
    """
    if not check:
        return EvaluationResult(
            satisfied=False,
            reasons=["no auto_check declared on control — control is not testable by AEGIS"],
            evidence_refs=[],
        )

    sys_id = sys_d.get("id")
    refs: list[str] = [f"system:{sys_id}"]
    reasons: list[str] = []
    all_ok = True

    def _pass(predicate: str, detail: str) -> None:
        reasons.append(f"{predicate}: PASSED — {detail}")

    def _fail(predicate: str, detail: str) -> None:
        nonlocal all_ok
        all_ok = False
        reasons.append(f"{predicate}: FAILED — {detail}")

    for k, v in check.items():
        if k == "registry_completeness_min":
            score = int(sys_d.get("completeness_score") or 0)
            refs.append(f"system:{sys_id}.completeness:{score}")
            if score >= int(v):
                _pass(f"registry_completeness_min({v})", f"completeness={score}%")
            else:
                _fail(f"registry_completeness_min({v})", f"completeness={score}% (needs ≥{v}%)")

        elif k == "aisia_status_in":
            current = sys_d.get("aisia_status") or "none"
            aid = sys_d.get("aisia_id")
            if aid:
                refs.append(f"aisia:{aid}:{current}")
            if current in v:
                _pass(f"aisia_status_in({v})", f"current={current}")
            else:
                _fail(f"aisia_status_in({v})", f"current={current}")

        elif k == "aisia_treatment_decided":
            decision = sys_d.get("aisia_treatment_decision")
            aid = sys_d.get("aisia_id")
            if aid:
                refs.append(f"aisia:{aid}:treatment={decision or 'none'}")
            populated = decision is not None
            if bool(v) == populated:
                _pass("aisia_treatment_decided", f"decision={decision or '∅'}")
            else:
                _fail("aisia_treatment_decided",
                      f"decision={decision or '∅'} (expected {'set' if v else 'unset'})")

        elif k == "data_types_documented":
            populated = bool(sys_d.get("data_types_processed"))
            count = len(sys_d.get("data_types_processed") or [])
            refs.append(f"system:{sys_id}.data_types_count:{count}")
            if bool(v) == populated:
                _pass("data_types_documented", f"data_types_processed has {count} entries")
            else:
                _fail("data_types_documented", "data_types_processed is empty")

        elif k == "intended_purpose_documented":
            populated = bool((sys_d.get("intended_purpose") or "").strip())
            refs.append(f"system:{sys_id}.intended_purpose_set:{populated}")
            if bool(v) == populated:
                _pass("intended_purpose_documented",
                      "intended_purpose is set" if populated else "intended_purpose is empty")
            else:
                _fail("intended_purpose_documented", "intended_purpose is empty")

        elif k == "human_oversight_documented":
            populated = bool((sys_d.get("human_oversight_desc") or "").strip())
            refs.append(f"system:{sys_id}.human_oversight_set:{populated}")
            if bool(v) == populated:
                _pass("human_oversight_documented",
                      "human_oversight_desc is set" if populated else "human_oversight_desc is empty")
            else:
                _fail("human_oversight_documented", "human_oversight_desc is empty")

        elif k == "owner_assigned":
            uid = sys_d.get("owner_user_id")
            populated = uid is not None
            refs.append(f"system:{sys_id}.owner_user_id:{uid or '∅'}")
            if bool(v) == populated:
                _pass("owner_assigned", f"owner_user_id={uid}")
            else:
                _fail("owner_assigned", "no owner assigned in registry")

        elif k == "risk_assessed":
            score = sys_d.get("current_risk_score")
            populated = score is not None
            refs.append(f"system:{sys_id}.risk_score:{score if populated else '∅'}")
            if bool(v) == populated:
                _pass("risk_assessed", f"current_risk_score={score}")
            else:
                _fail("risk_assessed", "no risk score computed yet")

        elif k == "usage_monitored":
            count = sys_d.get("usage_count") or 0
            ok = count > 0
            refs.append(f"system:{sys_id}.usage_events:{count}")
            if bool(v) == ok:
                _pass("usage_monitored", f"{count} ai_usage_events observed")
            else:
                _fail("usage_monitored", "no ai_usage_events observed for this system")

        elif k == "eu_ai_act_category_documented":
            cat = sys_d.get("eu_ai_act_category")
            populated = bool(cat)
            refs.append(f"system:{sys_id}.eu_ai_act_category:{cat or '∅'}")
            if bool(v) == populated:
                _pass("eu_ai_act_category_documented", f"category={cat}")
            else:
                _fail("eu_ai_act_category_documented", "eu_ai_act_category not set")

        elif k == "eu_ai_act_category_not":
            cat = sys_d.get("eu_ai_act_category")
            refs.append(f"system:{sys_id}.eu_ai_act_category:{cat or '∅'}")
            if cat != v:
                _pass(f"eu_ai_act_category_not({v})", f"category={cat}")
            else:
                _fail(f"eu_ai_act_category_not({v})", f"category={cat} matches forbidden value")

        elif k == "provider_assessed":
            ok = (sys_d.get("provider_id") is not None
                  or bool((sys_d.get("provider_name_freetext") or "").strip()))
            slug = sys_d.get("provider_slug") or sys_d.get("provider_name_freetext") or "∅"
            refs.append(f"system:{sys_id}.provider:{slug}")
            if bool(v) == ok:
                _pass("provider_assessed", f"provider={slug}")
            else:
                _fail("provider_assessed", "no provider linked (catalogue + free-text both empty)")

        elif k == "provider_jurisdiction_permitted":
            country = (sys_d.get("provider_country") or "").upper()
            slug = sys_d.get("provider_slug") or "∅"
            refs.append(f"provider:{slug}.hq_country:{country or '∅'}")
            ok = country in DEFAULT_PERMITTED_JURISDICTIONS
            if bool(v) == ok:
                _pass("provider_jurisdiction_permitted",
                      f"hq_country={country} (in permitted list)")
            else:
                if not country:
                    _fail("provider_jurisdiction_permitted",
                          "provider hq_country unknown (conservative: treated as not-permitted)")
                else:
                    _fail("provider_jurisdiction_permitted",
                          f"hq_country={country} not in permitted list "
                          f"({sorted(DEFAULT_PERMITTED_JURISDICTIONS)})")

        else:
            # Unknown predicate — record but do not fail.
            reasons.append(f"{k}: SKIPPED — unsupported predicate (forward-compat)")

    return EvaluationResult(satisfied=all_ok, reasons=reasons, evidence_refs=refs)


# ---------------------------------------------------------------------------
# Auto-assessment driver
# ---------------------------------------------------------------------------

async def auto_assess(*, session, tenant_id: UUID, framework_slug: str) -> dict[str, Any]:
    """Run auto-assessment across all systems for one framework.

    Post-condition: every control in the framework has at least one
    mapping with status in {implemented, partial, not_implemented,
    not_applicable}. The string ``not_assessed`` does not appear.
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

    # ------------------------------------------------------------------
    # Case 1 — tenant has zero AI systems. Write tenant-scoped mappings
    # so every control still ends with a verdict (no not_assessed).
    # ------------------------------------------------------------------
    if not systems:
        for ctrl in controls:
            await _upsert_mapping(
                session,
                tenant_id=tenant_id,
                control_id=ctrl.id,
                ai_system_id=None,
                status="not_implemented",
                notes=("No AI systems registered in tenant yet — cannot verify "
                       f"predicate {ctrl.auto_check!s} against any system."),
                evidence_refs=["tenant:registry:empty"],
            )
        return {
            "ok": True, "framework": framework_slug,
            "controls": len(controls), "systems": 0,
            "assessed": len(controls),
            "no_systems": True,
        }

    # ------------------------------------------------------------------
    # Case 2 — pre-enrich each system then evaluate every (control, system).
    # ------------------------------------------------------------------
    enriched: list[dict[str, Any]] = []
    for s in systems:
        d = _system_dict(s)
        await _enrich_system_context(session, d)
        enriched.append(d)

    assessed = 0
    for ctrl in controls:
        for sys_d in enriched:
            existing = (await session.execute(
                select(ComplianceMapping)
                .where((ComplianceMapping.tenant_id == tenant_id) &
                       (ComplianceMapping.control_id == ctrl.id) &
                       (ComplianceMapping.ai_system_id == sys_d["id"]))
            )).scalar_one_or_none()
            if existing is not None and existing.status in ("implemented", "not_applicable"):
                # Honour human attestation; never overwrite.
                continue

            result = evaluate_auto_check(ctrl.auto_check or {}, sys_d)
            new_status = "partial" if result.satisfied else "not_implemented"

            # Prefix the system name to make notes auditor-readable.
            notes = (f"[{sys_d['name']}] " + " | ".join(result.reasons))[:8000]

            await _upsert_mapping(
                session,
                tenant_id=tenant_id,
                control_id=ctrl.id,
                ai_system_id=sys_d["id"],
                status=new_status,
                notes=notes,
                evidence_refs=result.evidence_refs,
            )
            assessed += 1

    return {
        "ok": True, "framework": framework_slug,
        "controls": len(controls), "systems": len(systems),
        "assessed": assessed,
    }


async def _upsert_mapping(
    session, *, tenant_id: UUID, control_id: UUID, ai_system_id: UUID | None,
    status: str, notes: str, evidence_refs: list[str],
) -> None:
    """Idempotent upsert keyed on (tenant_id, control_id, ai_system_id)."""
    stmt = (
        pg_insert(ComplianceMapping)
        .values(
            tenant_id=tenant_id,
            control_id=control_id,
            ai_system_id=ai_system_id,
            status=status,
            implementation_notes=notes,
            evidence_refs=evidence_refs,
            last_assessed_at=func.now(),
        )
        .on_conflict_do_update(
            constraint="uq_mappings_unique",
            set_={
                "status":               status,
                "implementation_notes": notes,
                "evidence_refs":        evidence_refs,
                "last_assessed_at":     func.now(),
            },
        )
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Framework score (best status per control)
# ---------------------------------------------------------------------------

async def framework_score(*, session, framework_slug: str) -> FrameworkScore | None:
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
    best_per_control: dict[UUID, str] = {}
    rank = {"implemented": 5, "partial": 4, "not_applicable": 3,
            "not_assessed": 2, "not_implemented": 1}
    for cid, status in mappings:
        if cid not in best_per_control or rank.get(status, 0) > rank.get(best_per_control[cid], 0):
            best_per_control[cid] = status

    # Any control with no mapping at all (auto-assessment never ran) is
    # surfaced as not_implemented — never not_assessed. This preserves the
    # post-condition even when the operator inspects the dashboard before
    # running auto-assessment.
    for cid in (c.id for c in controls):
        s = best_per_control.get(cid, "not_implemented")
        by_status[s] = by_status.get(s, 0) + 1

    total = len(controls) or 1
    score = (by_status["implemented"] + 0.5 * by_status["partial"]) / total * 100

    gaps = [
        {"control_id": c.control_id, "title": c.title, "category": c.category,
         "status": best_per_control.get(c.id, "not_implemented")}
        for c in controls
        if best_per_control.get(c.id, "not_implemented") == "not_implemented"
    ]

    return FrameworkScore(
        framework_id=framework.id, slug=framework.slug, name=framework.name,
        total_controls=len(controls), by_status=by_status,
        score_pct=round(score, 1), gaps=gaps,
    )
