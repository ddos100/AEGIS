"""Verification cadence helper — locked-in tight schedule per the
PHASE-7-PLAN.md §6 decision."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.verification_cadence import next_due


def _delta(severity: str | None) -> timedelta:
    before = datetime.now(timezone.utc)
    due = next_due(severity)
    return due - before


def test_critical_is_fifteen_minutes() -> None:
    # Tolerate a tiny clock drift between the two now() calls.
    d = _delta("critical")
    assert timedelta(minutes=14, seconds=58) <= d <= timedelta(minutes=15, seconds=2)


def test_high_is_one_hour() -> None:
    d = _delta("high")
    assert timedelta(minutes=59, seconds=58) <= d <= timedelta(hours=1, seconds=2)


def test_medium_is_six_hours() -> None:
    d = _delta("medium")
    assert timedelta(hours=5, minutes=59) <= d <= timedelta(hours=6, seconds=2)


def test_low_is_twenty_four_hours() -> None:
    d = _delta("low")
    assert timedelta(hours=23, minutes=59) <= d <= timedelta(hours=24, seconds=2)


def test_unknown_severity_defaults_to_low() -> None:
    d = _delta("UNKNOWN-OR-NEW")
    assert d >= timedelta(hours=23, minutes=59)


def test_none_severity_defaults_to_low() -> None:
    d = _delta(None)
    assert d >= timedelta(hours=23, minutes=59)


def test_case_insensitive() -> None:
    a = _delta("CRITICAL")
    b = _delta("critical")
    # Both should fall in the 15-minute bucket
    assert timedelta(minutes=14, seconds=58) <= a <= timedelta(minutes=15, seconds=2)
    assert timedelta(minutes=14, seconds=58) <= b <= timedelta(minutes=15, seconds=2)
