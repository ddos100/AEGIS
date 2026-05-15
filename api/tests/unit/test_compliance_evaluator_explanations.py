"""Verify the engine produces auditor-readable reasons + evidence refs."""
from __future__ import annotations

from uuid import uuid4

from app.services.compliance_engine import evaluate_auto_check


def _sys(**over) -> dict:
    defaults = dict(
        id=uuid4(), name="acme-chatbot", completeness_score=0,
        aisia_status="not_started", data_types_processed=[], intended_purpose=None,
        human_oversight_desc=None, owner_user_id=None,
        current_risk_score=None, eu_ai_act_category=None,
        provider_name_freetext=None, catalogue_service_id=None,
        provider_id=None, provider_slug=None, aisia_id=None,
        aisia_treatment_decision=None, provider_country=None, usage_count=0,
    )
    defaults.update(over)
    return defaults


def test_passed_predicate_carries_observation() -> None:
    sys = _sys(completeness_score=85)
    r = evaluate_auto_check({"registry_completeness_min": 60}, sys)
    assert r.satisfied is True
    assert any("PASSED" in line and "completeness=85%" in line for line in r.reasons)
    assert f"system:{sys['id']}.completeness:85" in r.evidence_refs


def test_failed_predicate_explains_gap() -> None:
    sys = _sys(completeness_score=42)
    r = evaluate_auto_check({"registry_completeness_min": 80}, sys)
    assert r.satisfied is False
    assert any("FAILED" in line and "needs ≥80%" in line for line in r.reasons)


def test_multiple_predicates_AND_with_one_failure() -> None:
    sys = _sys(owner_user_id=uuid4(), data_types_processed=[])
    r = evaluate_auto_check(
        {"owner_assigned": True, "data_types_documented": True}, sys
    )
    assert r.satisfied is False
    joined = "\n".join(r.reasons)
    assert "owner_assigned: PASSED" in joined
    assert "data_types_documented: FAILED" in joined


def test_evidence_refs_include_system_id() -> None:
    sys = _sys(owner_user_id=uuid4())
    r = evaluate_auto_check({"owner_assigned": True}, sys)
    assert any(ref.startswith(f"system:{sys['id']}") for ref in r.evidence_refs)


def test_empty_check_explanation() -> None:
    r = evaluate_auto_check({}, _sys())
    assert r.satisfied is False
    assert any("not testable" in line for line in r.reasons)


def test_provider_jurisdiction_unknown_country_explanation() -> None:
    r = evaluate_auto_check({"provider_jurisdiction_permitted": True},
                            _sys(provider_country=None))
    assert r.satisfied is False
    assert any("conservative" in line.lower() for line in r.reasons)
