"""Risk engine unit tests — exhaustive over each dimension."""
from __future__ import annotations

import pytest

from app.services.risk_engine import (
    DIMENSION_WEIGHTS,
    compute_risk_score,
)


def _base_system(**over) -> dict:
    return {
        "name": "Test", "category": "llm",
        "data_types_processed": [],
        "affected_data_subjects": [],
        "user_population": None,
        "eu_ai_act_category": None,
        "geographic_scope": [],
        "compliance_flags": {},
        **over,
    }


def test_weights_sum_to_one() -> None:
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001


def test_empty_system_scores_low() -> None:
    s = compute_risk_score(_base_system())
    assert 0 <= s.total <= 30
    assert s.risk_level in ("low", "medium")


def test_biometric_data_dominates_sensitivity() -> None:
    s = compute_risk_score(_base_system(data_types_processed=["biometric"]))
    assert s.data_sensitivity == 100


def test_internal_data_low_sensitivity() -> None:
    s = compute_risk_score(_base_system(data_types_processed=["internal"]))
    assert s.data_sensitivity == 30


def test_max_data_type_wins() -> None:
    s = compute_risk_score(_base_system(data_types_processed=["public", "health", "internal"]))
    assert s.data_sensitivity == 90    # health


def test_agent_category_drives_capability() -> None:
    s = compute_risk_score(_base_system(category="agent"))
    assert s.ai_capability >= 90


def test_eu_ai_act_unacceptable_pushes_regulatory_max() -> None:
    s = compute_risk_score(_base_system(eu_ai_act_category="unacceptable"))
    assert s.regulatory_exposure == 100


def test_financial_data_triggers_rbi_flag_implicit() -> None:
    s = compute_risk_score(_base_system(data_types_processed=["financial"]))
    # Implicit India-sector heuristic: financial → rbi_regulated (score 90)
    assert s.regulatory_exposure == 90
    assert "rbi_regulated" in s.inputs.get("regulatory_flags", [])


def test_public_subjects_push_access_scope_to_max() -> None:
    s = compute_risk_score(_base_system(affected_data_subjects=["public"]))
    assert s.access_scope == 100


def test_provider_trust_inverted_from_catalogue() -> None:
    cat = {"risk_hints": {"provider_trust_score": 90}, "capabilities": ["text_generation"]}
    s = compute_risk_score(_base_system(), catalogue=cat)
    # 100 - 90 = 10
    assert s.provider_trust == 10


def test_unknown_provider_defaults_moderate() -> None:
    s = compute_risk_score(_base_system())
    assert s.provider_trust == 60


def test_critical_combo_lands_critical() -> None:
    s = compute_risk_score(_base_system(
        category="agent",
        data_types_processed=["biometric"],
        eu_ai_act_category="high_risk",
        affected_data_subjects=["public"],
    ))
    assert s.risk_level == "critical"
    assert s.total >= 75


def test_narrative_flag_only_for_high_critical() -> None:
    low = compute_risk_score(_base_system())
    assert low.needs_narrative is False
    critical = compute_risk_score(_base_system(
        category="agent",
        data_types_processed=["biometric"],
        eu_ai_act_category="high_risk",
        affected_data_subjects=["public"],
    ))
    assert critical.needs_narrative is True


def test_total_capped_at_100() -> None:
    # Even maximally adversarial inputs cap at 100.
    s = compute_risk_score(_base_system(
        category="agent",
        data_types_processed=["biometric", "health"],
        eu_ai_act_category="unacceptable",
        affected_data_subjects=["public"],
        compliance_flags={"rbi": True, "irdai": True, "sebi": True, "dpdpa": True},
    ))
    assert s.total <= 100


def test_inputs_audit_trail_populated() -> None:
    s = compute_risk_score(_base_system(
        data_types_processed=["personal"], affected_data_subjects=["customers"]))
    assert s.inputs["data_types_processed"] == ["personal"]
    assert "access_scope_basis" in s.inputs


@pytest.mark.parametrize("eu_cat,expected_min", [
    ("unacceptable", 100),
    ("high_risk",     90),
    ("limited_risk",  20),
    ("minimal_risk",  10),
])
def test_eu_ai_act_mapping(eu_cat: str, expected_min: int) -> None:
    s = compute_risk_score(_base_system(eu_ai_act_category=eu_cat))
    assert s.regulatory_exposure >= expected_min
