"""Celery application + beat schedule.

Beat jobs:
  - heartbeat        every minute   liveness signal
  - rebuild_matcher  every 4 hours  reload Aho-Corasick automaton from DB

Worker startup also loads every registered normalizer so the discovery
ingest pipeline can dispatch by source string.
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
}


@worker_process_init.connect
def _on_worker_init(**_kwargs) -> None:
    """Eagerly import every normalizer module on worker boot.

    Without this the @register decorators don't fire until the first task hits
    the module, which would lose the first batch of any new source.
    """
    from app.integrations.network.base import load_all_normalizers
    load_all_normalizers()
