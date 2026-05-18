"""Celery tasks.

Phase 0  — heartbeat
Phase 2  — log-batch ingest (network + XDR + extension), matcher rebuild
Phase 3  — scheduled integration sync (Entra/Okta/AWS/M365/...)
Phase 4  — daily risk recalc + AISIA auto-trigger for Critical/High
"""
from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Any
from uuid import UUID

from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    log.info("aegis.beat.heartbeat", at=now)
    return {"status": "ok", "at": now}


@celery_app.task(name="app.workers.tasks.process_log_batch", bind=True, max_retries=3)
def process_log_batch(self, tenant_id: str, source: str, events: list[Any]) -> dict[str, int]:
    """Off-main-thread batch processing for high-volume ingest.

    The API endpoint also calls the underlying coroutine directly for small
    batches (< 200 events) to avoid the broker round-trip. Larger batches land
    here.
    """
    from app.workers.ingest import process_batch

    try:
        return asyncio.run(process_batch(
            tenant_id=UUID(tenant_id),
            source=source,
            events=events,
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.ingest.batch_failed", error=str(exc), source=source,
                    tenant_id=tenant_id)
        raise self.retry(exc=exc, countdown=min(60 * (self.request.retries + 1), 600))


@celery_app.task(name="app.workers.tasks.rebuild_matcher")
def rebuild_matcher() -> dict[str, int]:
    """Reload the Aho-Corasick automaton from the DB. Called from the catalogue
    importer on completion and from a daily Celery beat job."""
    from app.integrations.network.matcher import load_from_db, matcher_size

    asyncio.run(load_from_db())
    size = matcher_size()
    log.info("aegis.matcher.rebuilt", **size)
    return size


# ============ Phase 3 — scheduled integration sync ============

@celery_app.task(name="app.workers.tasks.sync_all_integrations")
def sync_all_integrations() -> dict[str, Any]:
    """Daily beat task: run every active integration for every tenant.

    The actual sync is delegated to :func:`sync_one_integration` so failures
    on a single integration don't poison the whole batch.
    """
    return asyncio.run(_sync_all())


async def _sync_all() -> dict[str, Any]:
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models.integration_credential import IntegrationCredential

    # Plain session — no RLS scope (we iterate ALL tenants).
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(IntegrationCredential.id, IntegrationCredential.tenant_id)
            .where(IntegrationCredential.status == "active")
        )).all()

    triggered = 0
    for row in rows:
        sync_one_integration.delay(str(row.tenant_id), str(row.id))
        triggered += 1
    log.info("aegis.integrations.sync_dispatched", count=triggered)
    return {"dispatched": triggered}


@celery_app.task(name="app.workers.tasks.sync_one_integration", bind=True, max_retries=2)
def sync_one_integration(self, tenant_id: str, integration_id: str) -> dict[str, Any]:
    """Run a single connector for a single tenant. Records the run result on the
    credential row (last_sync_at / last_sync_result / last_error / status)."""
    try:
        return asyncio.run(_sync_one(UUID(tenant_id), UUID(integration_id)))
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.integrations.sync_failed",
                    tenant_id=tenant_id, integration_id=integration_id, error=str(exc))
        raise self.retry(exc=exc, countdown=600)


async def _sync_one(tenant_id: UUID, integration_id: UUID) -> dict[str, Any]:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.core.crypto import decrypt_credentials
    from app.core.database import session_scope
    from app.integrations.connectors import get_connector
    from app.models.integration_credential import IntegrationCredential

    async with session_scope(tenant_id=tenant_id) as session:
        row = (await session.execute(
            select(IntegrationCredential).where(IntegrationCredential.id == integration_id)
        )).scalar_one_or_none()
        if row is None:
            return {"ok": False, "error": "integration not found"}

        try:
            connector = get_connector(row.integration)
            creds = decrypt_credentials(row.credentials_ciphertext)
        except Exception as exc:  # noqa: BLE001
            row.last_error = f"resolve failed: {exc}"
            row.status = "error"
            return {"ok": False, "error": row.last_error}

        result = await connector.sync(
            creds, tenant_id=tenant_id, integration_id=row.id, session=session,
        )
        row.last_sync_at = datetime.now(timezone.utc)
        row.last_used_at = row.last_sync_at
        row.last_sync_result = {
            "ok":               result.ok,
            "discovered_count": result.discovered_count,
            "new_count":        result.new_count,
            "updated_count":    result.updated_count,
            "extra":            result.extra,
        }
        row.last_error = result.error
        row.status = "active" if result.ok else "error"
        return {"ok": result.ok, "discovered": result.discovered_count}


# ============ Phase 4 — daily risk recalc ============

@celery_app.task(name="app.workers.tasks.recalculate_all_risk")
def recalculate_all_risk() -> dict[str, Any]:
    """Beat task: dispatch a per-system risk recalc for every AISystem."""
    return asyncio.run(_recalc_all())


async def _recalc_all() -> dict[str, Any]:
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models.ai_system import AISystem

    # No RLS scope — iterate every system across every tenant.
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AISystem.id, AISystem.tenant_id)
        )).all()

    dispatched = 0
    for r in rows:
        recalc_one_system.delay(str(r.tenant_id), str(r.id))
        dispatched += 1
    log.info("aegis.risk.recalc_dispatched", count=dispatched)
    return {"dispatched": dispatched}


@celery_app.task(name="app.workers.tasks.recalc_one_system", bind=True, max_retries=2)
def recalc_one_system(self, tenant_id: str, system_id: str) -> dict[str, Any]:
    """Recalculate risk for a single system + auto-create an AISIA record
    when the system lands in Critical or High and doesn't already have one."""
    try:
        return asyncio.run(_recalc_one(UUID(tenant_id), UUID(system_id)))
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.risk.recalc_failed",
                    tenant_id=tenant_id, system_id=system_id, error=str(exc))
        raise self.retry(exc=exc, countdown=300)


async def _recalc_one(tenant_id: UUID, system_id: UUID) -> dict[str, Any]:
    from sqlalchemy import select
    from app.core.database import session_scope
    from app.integrations.claude.client import generate_risk_narrative
    from app.models.ai_service import AIService
    from app.models.ai_system import AISystem
    from app.models.aisia_record import AISIARecord
    from app.models.risk_assessment import RiskAssessment
    from app.services.risk_engine import compute_risk_score

    async with session_scope(tenant_id=tenant_id) as session:
        system = (await session.execute(
            select(AISystem).where(AISystem.id == system_id)
        )).scalar_one_or_none()
        if system is None:
            return {"ok": False, "error": "system not found"}

        catalogue = None
        if system.catalogue_service_id:
            cat = (await session.execute(
                select(AIService).where(AIService.id == system.catalogue_service_id)
            )).scalar_one_or_none()
            if cat is not None:
                catalogue = {
                    "capabilities": cat.capabilities,
                    "risk_hints":   cat.risk_hints,
                    "provider_id":  cat.provider_id,
                }

        system_dict = {
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
        }
        score = compute_risk_score(system_dict, catalogue=catalogue)

        narrative = None
        if score.risk_level in ("critical", "high"):
            narrative = await generate_risk_narrative(system_dict, {
                "data_sensitivity":    score.data_sensitivity,
                "ai_capability":       score.ai_capability,
                "regulatory_exposure": score.regulatory_exposure,
                "access_scope":        score.access_scope,
                "provider_trust":      score.provider_trust,
                "total":               score.total,
                "risk_level":          score.risk_level,
            })

        now = datetime.now(UTC)
        session.add(RiskAssessment(
            tenant_id=tenant_id, ai_system_id=system.id,
            data_sensitivity_score=score.data_sensitivity,
            ai_capability_score=score.ai_capability,
            regulatory_exposure_score=score.regulatory_exposure,
            access_scope_score=score.access_scope,
            provider_trust_score=score.provider_trust,
            total_score=score.total, risk_level=score.risk_level,
            scoring_inputs=score.inputs, ai_narrative=narrative,
            ai_model_used="claude-sonnet-4-6" if narrative else None,
            calculated_by="auto", calculated_at=now,
        ))
        system.current_risk_score = score.total
        system.last_risk_assessed_at = now

        # Auto-trigger AISIA for Critical/High systems with no existing record.
        if score.risk_level in ("critical", "high"):
            existing = (await session.execute(
                select(AISIARecord.id).where(AISIARecord.ai_system_id == system.id)
            )).scalar_one_or_none()
            if existing is None:
                session.add(AISIARecord(
                    tenant_id=tenant_id, ai_system_id=system.id,
                    status="initiated", initiated_at=now,
                ))
                system.aisia_status = "initiated"

    return {"ok": True, "total": score.total, "level": score.risk_level}


# ============ Phase 7.5 — mitigation verification scheduler ============

@celery_app.task(name="app.workers.tasks.verify_due_mitigations")
def verify_due_mitigations() -> dict[str, Any]:
    """Walk every `applied`/`verified`/`drifted` mitigation_actions row
    whose `verification_due_at` is now-or-past and re-run the registered
    adapter's verify(). Re-schedules per the locked severity cadence
    (15 m critical / 1 h high / 6 h medium / 24 h low).

    Runs every 15 min via Celery beat.
    """
    return asyncio.run(_verify_due())


async def _verify_due() -> dict[str, Any]:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.core.database import session_scope, SessionLocal
    from app.core.crypto import decrypt_credentials
    from app.integrations.mitigations import get_adapter
    from app.models.integration_credential import IntegrationCredential
    from app.models.mitigation_action import MitigationAction
    from app.models.threat import Threat
    from app.services.verification_cadence import next_due

    now = datetime.now(timezone.utc)

    # Pull due rows + their tenant_ids without RLS (system-level beat).
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(MitigationAction.id, MitigationAction.tenant_id)
            .where(
                (MitigationAction.status.in_(("applied", "verified", "drifted"))) &
                (MitigationAction.verification_due_at.is_not(None)) &
                (MitigationAction.verification_due_at <= now)
            )
            .order_by(MitigationAction.verification_due_at)
            .limit(500)
        )).all()

    totals: dict[str, int] = {"considered": len(rows), "verified": 0, "drifted": 0,
                                "missing": 0, "errored": 0}
    for mit_id, tenant_id in rows:
        try:
            async with session_scope(tenant_id=tenant_id) as session:
                row = (await session.execute(
                    select(MitigationAction).where(MitigationAction.id == mit_id)
                )).scalar_one()
                threat = (await session.execute(
                    select(Threat).where(Threat.id == row.threat_id)
                )).scalar_one()
                try:
                    adapter = get_adapter(row.integration, row.action)
                except KeyError:
                    row.last_error = f"Adapter ({row.integration},{row.action}) not registered"
                    totals["errored"] += 1
                    continue
                # Look up credentials within tenant scope.
                cred_row = (await session.execute(
                    select(IntegrationCredential)
                    .where((IntegrationCredential.integration == row.integration) &
                           (IntegrationCredential.status == "active"))
                    .limit(1)
                )).scalar_one_or_none()
                creds = None
                if cred_row is not None:
                    try:
                        creds = decrypt_credentials(cred_row.credentials_ciphertext)
                    except Exception:  # noqa: BLE001
                        row.last_error = "credentials decryption failed"
                        totals["errored"] += 1
                        continue
                result = await adapter.verify(
                    credentials=creds, params=row.params or {}, state_blob=row.state_blob,
                )
                if result.verified and not result.drifted and not result.missing:
                    row.status = "verified"
                    row.verified_at = now
                    row.last_error = None
                    totals["verified"] += 1
                elif result.drifted or result.missing:
                    row.status = "drifted"
                    row.last_error = result.detail or "drift detected"
                    totals["drifted" if result.drifted else "missing"] += 1
                elif result.error:
                    row.last_error = result.error
                    totals["errored"] += 1
                row.verification_due_at = next_due(threat.severity)
        except Exception as exc:  # noqa: BLE001
            totals["errored"] += 1
            log.error("aegis.mitigation.verify.error", id=str(mit_id), error=str(exc))
    log.info("aegis.mitigation.verify.cycle", **totals)
    return totals


# ============ Phase 7.2 — threat feed ingest ============

@celery_app.task(name="app.workers.tasks.ingest_threat_feeds")
def ingest_threat_feeds() -> dict[str, Any]:
    """Hourly: walk every registered feed normalizer, write drafts to
    the admin review queue."""
    return asyncio.run(_ingest_feeds())


async def _ingest_feeds() -> dict[str, Any]:
    from app.core.database import SessionLocal
    from app.services.threat_feed_ingest import ingest_all_sources

    async with SessionLocal() as session:
        # No tenant_id — threats catalogue + drafts are global.
        results = await ingest_all_sources(session=session)
        await session.commit()
    log.info("aegis.feed.ingest.cycle", results=results)
    return {"results": results}
