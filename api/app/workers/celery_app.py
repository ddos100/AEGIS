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
    # Phase 4 — daily risk recalc 03:00 UTC (after integration sync settles).
    # The deep daily recalc walks every system, refreshes the Claude
    # narrative on Critical/High, auto-creates AISIA records when none
    # exist.
    "recalculate-risk": {
        "task": "app.workers.tasks.recalculate_all_risk",
        "schedule": crontab(minute="0", hour="3"),
    },
    # Phase 7.6+ — hourly lightweight risk recalc at HH:25 so newly
    # auto-registered shadow systems (from network ingest, EA discovery,
    # or browser extension) get a risk score + AISIA trigger within
    # one hour instead of waiting for the daily 03:00 deep pass.
    # The same task is used; AISIA auto-creation is idempotent (insert-
    # if-missing).
    "recalculate-risk-hourly": {
        "task": "app.workers.tasks.recalculate_all_risk",
        "schedule": crontab(minute="25"),
    },
    # Phase 7.5 — verification scheduler runs every 15 min and walks
    # mitigation_actions where verification_due_at <= now(). Severity-
    # tiered cadence (15m critical / 1h high / 6h medium / 24h low) is
    # encoded on each row by `verification_cadence.next_due()`.
    "mitigation-verify-due": {
        "task": "app.workers.tasks.verify_due_mitigations",
        "schedule": crontab(minute="*/15"),
    },
    # Phase 7.2 — threat feed ingest runs hourly at HH:05. Pulls each
    # registered normalizer (MITRE ATLAS, OSV, AIID, ...) and writes
    # drafts to the admin review queue. Re-ingest is idempotent.
    "threat-feed-ingest": {
        "task": "app.workers.tasks.ingest_threat_feeds",
        "schedule": crontab(minute="5"),
    },
    # Phase 7.3 — exposure recompute every 10 min. Without this the
    # /exposures and /mitigations panels stay empty until an admin
    # clicks "Recompute exposures" by hand — new Registry rows from
    # network ingest / EA discovery would never propagate.
    # recompute_all() is idempotent (UPSERT keyed on
    # (tenant_id, threat_id)) and the orchestrator-propose path is
    # idempotent too (idempotency_key on mitigation_actions). Cheap
    # to run frequently.
    "exposure-recompute": {
        "task": "app.workers.tasks.recompute_all_exposures",
        "schedule": crontab(minute="*/10"),
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
