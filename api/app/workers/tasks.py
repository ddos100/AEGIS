"""Celery tasks.

Phase 0  — heartbeat
Phase 2  — log-batch ingest (network + XDR + extension), matcher rebuild
Phase 3  — scheduled integration sync (Entra/Okta/AWS/M365/...)
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
