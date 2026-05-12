"""Celery tasks. Phase 0 only contains a heartbeat for liveness verification."""
from __future__ import annotations

from datetime import datetime, UTC

from app.core.logging import log
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    log.info("aegis.beat.heartbeat", at=now)
    return {"status": "ok", "at": now}
