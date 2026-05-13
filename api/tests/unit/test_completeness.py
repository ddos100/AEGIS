"""Completeness scoring unit tests.

Mirror the Postgres plpgsql function in app/services/completeness.py and
confirm both halves of the matrix: which fields contribute, and the score
caps at 100.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.completeness import compute_completeness


def _empty_system() -> dict:
    """Baseline system dict — all completeness fields unpopulated."""
    return {
        "intended_purpose": None,
        "owner_user_id": None,
        "department_id": None,
        "data_types_processed": [],
        "affected_data_subjects": [],
        "deployment_type": None,
        "first_deployed_at": None,
        "human_oversight_desc": None,
        "output_type": None,
        "eu_ai_act_category": None,
        "geographic_scope": [],
        "user_population": None,
        "aisia_status": "not_started",
    }


def test_empty_system_scores_zero() -> None:
    assert compute_completeness(_empty_system()) == 0


def test_full_system_caps_at_100() -> None:
    full = {
        "intended_purpose": "Summarise customer service tickets",
        "owner_user_id": uuid4(),
        "department_id": uuid4(),
        "data_types_processed": ["personal"],
        "affected_data_subjects": ["customers"],
        "deployment_type": "cloud_saas",
        "first_deployed_at": "2026-01-01",
        "human_oversight_desc": "Human reviews every summary > $1k impact",
        "output_type": "summary",
        "eu_ai_act_category": "limited_risk",
        "geographic_scope": ["IN", "US"],
        "user_population": "Support team (~40 agents)",
        "aisia_status": "completed",
    }
    assert compute_completeness(full) == 100


@pytest.mark.parametrize("field,expected_weight", [
    ("intended_purpose",       15),
    ("owner_user_id",          10),
    ("department_id",          10),
    ("data_types_processed",   10),
    ("affected_data_subjects", 10),
    ("deployment_type",         5),
    ("first_deployed_at",       5),
    ("human_oversight_desc",   10),
    ("output_type",             5),
    ("eu_ai_act_category",      5),
    ("geographic_scope",        5),
    ("user_population",         5),
])
def test_single_field_contribution(field: str, expected_weight: int) -> None:
    s = _empty_system()
    s[field] = ["personal"] if field in {"data_types_processed", "affected_data_subjects",
                                          "geographic_scope"} else (
                  uuid4() if field.endswith("_id") else
                  "non-empty value" if isinstance(s[field], (str, type(None))) else s[field]
              )
    # first_deployed_at expects something date-like; "2026-01-01" works for predicate
    if field == "first_deployed_at":
        s[field] = "2026-01-01"
    assert compute_completeness(s) == expected_weight


def test_aisia_not_started_contributes_zero() -> None:
    s = _empty_system()
    s["aisia_status"] = "not_started"
    assert compute_completeness(s) == 0


def test_aisia_started_contributes_5() -> None:
    s = _empty_system()
    s["aisia_status"] = "in_progress"
    assert compute_completeness(s) == 5


def test_empty_string_treated_as_unpopulated() -> None:
    s = _empty_system()
    s["intended_purpose"] = ""
    assert compute_completeness(s) == 0
