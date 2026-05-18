"""Verification cadence helper — Phase 7.5 locked decision.

Tight cadence per locked plan (PHASE-7-PLAN.md §6):

    critical → 15 min
    high     → 1 h
    medium   → 6 h
    low      → 24 h

The verification scheduler reads `verification_due_at` and re-runs the
adapter's verify() for any row that's due. Each successful verification
re-schedules the row according to its threat severity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def next_due(severity: str | None) -> datetime:
    """Return the next verification timestamp from now() based on severity."""
    now = datetime.now(timezone.utc)
    delta = {
        "critical": timedelta(minutes=15),
        "high":     timedelta(hours=1),
        "medium":   timedelta(hours=6),
        "low":      timedelta(hours=24),
    }.get((severity or "low").lower(), timedelta(hours=24))
    return now + delta
