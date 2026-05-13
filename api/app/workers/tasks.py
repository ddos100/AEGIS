"""Celery tasks.

Phase 0  — heartbeat
Phase 2  — log-batch ingest (network + XDR + extension), matcher rebuild
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
