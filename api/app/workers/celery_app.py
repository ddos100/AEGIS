"""Celery application + beat schedule.

Beat jobs:
  - heartbeat            every minute   liveness signal
  - rebuild_matcher      every 4 hours  reload Aho-Corasick automaton from DB
  - sync_all_integrations  daily 02:00  per-tenant connector sync

Worker startup also loads every registered normalizer and connector so the
ingest + connector dispatch paths can resolve by source/integration key.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.core.config import settings

celery_app = Celery(
    "aegis",
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend),
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=4,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "heartbeat": {
        "task": "app.workers.tasks.heartbeat",
        "schedule": crontab(minute="*"),
    },
    "rebuild-matcher": {
        "task": "app.workers.tasks.rebuild_matcher",
        "schedule": crontab(minute="0", hour="*/4"),
    },
    "sync-integrations": {
        "task": "app.workers.tasks.sync_all_integrations",
        "schedule": crontab(minute="0", hour="2"),
    },
    # Phase 4 — daily risk recalc 03:00 UTC (after integration sync settles)
    "recalculate-risk": {
        "task": "app.workers.tasks.recalculate_all_risk",
        "schedule": crontab(minute="0", hour="3"),
    },
    # Phase 7.5 — verification scheduler runs every 15 min and walks
    # mitigation_actions where verification_due_at <= now(). Severity-
    # tiered cadence (15m critical / 1h high / 6h medium / 24h low) is
    # encoded on each row by `verification_cadence.next_due()`.
    "mitigation-verify-due": {
        "task": "app.workers.tasks.verify_due_mitigations",
        "schedule": crontab(minute="*/15"),
    },
}


@worker_process_init.connect
def _on_worker_init(**_kwargs) -> None:
    """Eagerly import every normalizer + connector module on worker boot.

    Without this the @register decorators don't fire until the first task hits
    the module, which would lose the first batch of any new source.
    """
    from app.integrations.network.base import load_all_normalizers
    from app.integrations.connectors import load_all_connectors
    load_all_normalizers()
    load_all_connectors()
