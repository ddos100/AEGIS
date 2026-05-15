"""Compliance auto_check predicate evaluator — pure-Python unit tests.

These cover the *predicate* layer only. The evaluator now returns an
``EvaluationResult`` (so the engine can attach explanations + evidence
to every mapping); the tests below assert behaviour through the
``.satisfied`` attribute. Reason + evidence shape is exercised by
``test_compliance_evaluator_explanations.py``.
"""
from __future__ import annotations

from uuid import uuid4

from app.services.compliance_engine import (
    DEFAULT_PERMITTED_JURISDICTIONS,
    evaluate_auto_check,
)


def _sys(**over) -> dict:
    defaults = dict(
        id=uuid4(), name="test-system", completeness_score=0, aisia_status="not_started",
        data_types_processed=[], intended_purpose=None,
        human_oversight_desc=None, owner_user_id=None,
        current_risk_score=None, eu_ai_act_category=None,
        provider_name_freetext=None, catalogue_service_id=None,
        provider_id=None,
        aisia_id=None, aisia_treatment_decision=None,
        provider_country=None, provider_slug=None, usage_count=0,
    )
    defaults.update(over)
    return defaults


def _ok(check, sys_d) -> bool:
    return evaluate_auto_check(check, sys_d).satisfied


def test_empty_check_returns_false() -> None:
    """No predicates → can't auto-mark as partial."""
    assert _ok({}, _sys()) is False


def test_completeness_threshold() -> None:
    assert _ok({"registry_completeness_min": 60}, _sys(completeness_score=80)) is True
    assert _ok({"registry_completeness_min": 60}, _sys(completeness_score=50)) is False


def test_aisia_status_in() -> None:
    pred = {"aisia_status_in": ["in_progress", "completed", "approved"]}
    assert _ok(pred, _sys(aisia_status="completed")) is True
    assert _ok(pred, _sys(aisia_status="not_started")) is False


def test_aisia_treatment_decided() -> None:
    pred = {"aisia_treatment_decided": True}
    assert _ok(pred, _sys(aisia_treatment_decision="accept")) is True
    assert _ok(pred, _sys(aisia_treatment_decision=None)) is False


def test_data_types_documented() -> None:
    pred = {"data_types_documented": True}
    assert _ok(pred, _sys(data_types_processed=["personal"])) is True
    assert _ok(pred, _sys(data_types_processed=[])) is False


def test_intended_purpose_documented() -> None:
    pred = {"intended_purpose_documented": True}
    assert _ok(pred, _sys(intended_purpose="Summarise tickets")) is True
    assert _ok(pred, _sys(intended_purpose=None)) is False
    assert _ok(pred, _sys(intended_purpose="   ")) is False


def test_owner_assigned() -> None:
    pred = {"owner_assigned": True}
    assert _ok(pred, _sys(owner_user_id=uuid4())) is True
    assert _ok(pred, _sys(owner_user_id=None)) is False


def test_risk_assessed() -> None:
    pred = {"risk_assessed": True}
    assert _ok(pred, _sys(current_risk_score=42)) is True
    assert _ok(pred, _sys(current_risk_score=None)) is False
    # Zero is a valid score — should count as assessed.
    assert _ok(pred, _sys(current_risk_score=0)) is True


def test_eu_ai_act_category_documented() -> None:
    pred = {"eu_ai_act_category_documented": True}
    assert _ok(pred, _sys(eu_ai_act_category="limited_risk")) is True
    assert _ok(pred, _sys(eu_ai_act_category=None)) is False


def test_eu_ai_act_category_not() -> None:
    pred = {"eu_ai_act_category_not": "unacceptable"}
    assert _ok(pred, _sys(eu_ai_act_category="high_risk")) is True
    assert _ok(pred, _sys(eu_ai_act_category="unacceptable")) is False
    # Unknown category passes (conservative — we can't disprove it isn't unacceptable)
    assert _ok(pred, _sys(eu_ai_act_category=None)) is True


def test_provider_assessed_via_catalogue() -> None:
    pred = {"provider_assessed": True}
    assert _ok(pred, _sys(provider_id=uuid4())) is True
    assert _ok(pred, _sys(provider_name_freetext="Acme AI")) is True
    assert _ok(pred, _sys()) is False


def test_provider_jurisdiction_permitted() -> None:
    pred = {"provider_jurisdiction_permitted": True}
    assert _ok(pred, _sys(provider_country="IN")) is True
    # Unknown country = conservative reject
    assert _ok(pred, _sys(provider_country=None)) is False
    assert _ok(pred, _sys(provider_country="CN")) is False
    for country in DEFAULT_PERMITTED_JURISDICTIONS:
        assert _ok(pred, _sys(provider_country=country)) is True


def test_usage_monitored() -> None:
    pred = {"usage_monitored": True}
    assert _ok(pred, _sys(usage_count=1)) is True
    assert _ok(pred, _sys(usage_count=0)) is False


def test_multiple_predicates_AND() -> None:
    """All keys in a single auto_check must pass."""
    pred = {"data_types_documented": True, "intended_purpose_documented": True,
            "owner_assigned": True}
    full = _sys(data_types_processed=["personal"], intended_purpose="Fraud detection",
                owner_user_id=uuid4())
    assert _ok(pred, full) is True
    full["owner_user_id"] = None
    assert _ok(pred, full) is False


def test_unknown_predicate_is_ignored() -> None:
    """Forward-compat: unknown keys don't fail the check."""
    pred = {"future_predicate": "whatever", "owner_assigned": True}
    assert _ok(pred, _sys(owner_user_id=uuid4())) is True
