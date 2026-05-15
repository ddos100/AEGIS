"""Policy engine unit tests — conditions matching only (no DB).

The end-to-end `evaluate()` flow that touches the session + violations table
lives in the integration suite (Phase 4 follow-up).
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.policy_engine import evaluate_conditions


def _system(**over):
    """Build a SimpleNamespace that quacks like AISystem for the matcher."""
    defaults = dict(
        id=uuid4(), category="llm", risk_level="medium", is_shadow=False,
        eu_ai_act_category=None, policy_status="allow",
        data_types_processed=["internal"],
        department_id=None,
    )
    defaults.update(over)
    return SimpleNamespace(**defaults)


def test_empty_conditions_match() -> None:
    ok, keys = evaluate_conditions({}, system=_system())
    assert ok is True
    assert keys == []


def test_ai_category_match() -> None:
    ok, _ = evaluate_conditions({"ai_category": ["llm", "agent"]}, system=_system(category="llm"))
    assert ok is True


def test_ai_category_mismatch() -> None:
    ok, _ = evaluate_conditions(
        {"ai_category": ["image_gen"]}, system=_system(category="llm")
    )
    assert ok is False


def test_risk_level_match() -> None:
    ok, _ = evaluate_conditions(
        {"risk_level": ["critical", "high"]}, system=_system(risk_level="critical")
    )
    assert ok is True


def test_data_classification_intersect() -> None:
    """system.data_types_processed includes ANY of the condition values."""
    ok, _ = evaluate_conditions(
        {"data_classification": ["biometric", "health"]},
        system=_system(data_types_processed=["personal", "health"]),
    )
    assert ok is True


def test_data_classification_no_overlap() -> None:
    ok, _ = evaluate_conditions(
        {"data_classification": ["biometric"]},
        system=_system(data_types_processed=["public"]),
    )
    assert ok is False


def test_is_shadow_match() -> None:
    ok_match, _ = evaluate_conditions({"is_shadow": True}, system=_system(is_shadow=True))
    ok_miss, _  = evaluate_conditions({"is_shadow": True}, system=_system(is_shadow=False))
    assert ok_match is True
    assert ok_miss is False


def test_user_group_requires_groups_to_be_supplied() -> None:
    ok, _ = evaluate_conditions(
        {"user_group": ["contractors"]}, system=_system(), user_groups=None,
    )
    assert ok is False
    ok2, _ = evaluate_conditions(
        {"user_group": ["contractors"]}, system=_system(),
        user_groups=["contractors", "employees"],
    )
    assert ok2 is True


def test_eu_ai_act_match() -> None:
    ok, _ = evaluate_conditions(
        {"eu_ai_act_category": ["unacceptable"]},
        system=_system(eu_ai_act_category="unacceptable"),
    )
    assert ok is True


def test_multiple_conditions_AND_semantics() -> None:
    # All keys must match.
    system = _system(category="llm", risk_level="critical", is_shadow=True,
                     data_types_processed=["personal"])
    ok, keys = evaluate_conditions(
        {
            "ai_category":         ["llm", "agent"],
            "risk_level":          ["critical", "high"],
            "is_shadow":           True,
            "data_classification": ["personal"],
        },
        system=system,
    )
    assert ok is True
    assert set(keys) == {"ai_category", "risk_level", "is_shadow", "data_classification"}


def test_multiple_conditions_one_mismatch_fails_all() -> None:
    system = _system(category="llm", risk_level="medium")
    ok, _ = evaluate_conditions(
        {"ai_category": ["llm"], "risk_level": ["critical"]},
        system=system,
    )
    assert ok is False


def test_case_insensitive_string_match() -> None:
    """Common operator error — Mixed-case category from a YAML import."""
    ok, _ = evaluate_conditions(
        {"ai_category": ["LLM"]}, system=_system(category="llm")
    )
    assert ok is True
