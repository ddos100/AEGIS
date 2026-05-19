"""Admin / platform-health endpoints.

  GET  /v1/admin/seed-status     Read-only: AI services + threats +
                                  frameworks + AI systems counts +
                                  remediation advice. Unauth-allowed?
                                  No — analyst+ JWT required because
                                  counts are tenant-aware-ish info.
  POST /v1/admin/reseed          Admin trigger: re-run every importer
                                  regardless of current table state.
                                  Used after editing the YAML files to
                                  push changes through without
                                  restarting the API container.
  POST /v1/admin/recompute-now   Admin trigger: fire the exposure +
                                  mitigation recompute + risk recalc
                                  for the calling user's tenant. Same
                                  effect as the periodic beats, just
                                  on-demand.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/seed-status")
async def seed_status_route(
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> dict[str, Any]:
    from app.services.auto_seed import seed_status
    return await seed_status()


@router.post("/reseed")
async def reseed_route(
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> dict[str, Any]:
    """Force-run every importer.

    The threats importer still enforces the .inventory_digest fixture
    (refuses to import when the YAML files have drifted from the pinned
    digest). The other two are unconditional upserts.

    After importers complete, the network-ingest matcher is rebuilt so
    newly-imported AI service patterns become active without an API
    restart — otherwise the matcher stays empty until the next process
    boot and Registry auto-registration would still not fire.
    """
    from app.services.auto_seed import force_reseed
    result = await force_reseed()

    # Rebuild the Aho-Corasick automaton against the freshly-imported
    # ai_services rows. Without this the in-memory matcher would still
    # be empty (or stale) and the network ingest path would silently
    # match nothing — exactly the symptom the reseed is supposed to fix.
    try:
        from app.integrations.network.matcher import load_from_db, matcher_size
        n = await load_from_db()
        result["matcher_reloaded"] = {"services_indexed": n, **matcher_size()}
    except Exception as exc:  # noqa: BLE001
        result["matcher_reloaded"] = {"ok": False, "error": str(exc)}

    return result


@router.post("/recompute-now")
async def recompute_now(
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Fire exposure-recompute + risk-recalc for THIS tenant right now.

    Same code paths as the periodic beats, just dispatched on-demand.
    Useful right after a `reseed` so the operator can see Registry +
    Exposures + Mitigations populated without waiting 10 minutes.

    Risk recalc is dispatched to Celery (one task per system) because
    the per-system path can call the Claude API for narrative
    generation and we don't want to block the HTTP request on that.
    """
    from sqlalchemy import select
    from app.models.ai_system import AISystem
    from app.services.exposure_engine import recompute_all

    # 1. Exposures + mitigations — sync, inline, runs against this
    #    tenant's RLS-scoped session.
    exposure_result = await recompute_all(session=db, tenant_id=user.tenant_id)

    # 2. Risk recalc — queue one task per system in this tenant.
    rows = (await db.execute(select(AISystem.id))).all()
    risk_dispatched = 0
    try:
        from app.workers.tasks import recalc_one_system
        for r in rows:
            recalc_one_system.delay(str(user.tenant_id), str(r[0]))
            risk_dispatched += 1
        risk_result: dict[str, Any] = {"dispatched": risk_dispatched,
                                        "note": "results land in 30-120s"}
    except Exception as exc:  # noqa: BLE001
        # Celery broker unreachable? Surface but don't fail the whole
        # endpoint — the exposure recompute above already succeeded.
        risk_result = {"ok": False, "error": str(exc),
                        "note": "Celery may be down; exposures still ran"}

    return {
        "exposures":   exposure_result,
        "risk_recalc": risk_result,
    }
