"""Celery application + Phase 0 heartbeat beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

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

# Phase 0 beat schedule: a single noop heartbeat proving beat is alive.
celery_app.conf.beat_schedule = {
    "heartbeat": {
        "task": "app.workers.tasks.heartbeat",
        "schedule": crontab(minute="*"),  # every minute
    },
}
