"""Exposure-evaluation engine — pure-Python predicate tests.

These cover the predicate dispatcher and the verdict aggregator.
Integration coverage that exercises the DB snapshot loader + recompute_all
upsert path lives in compose-based e2e tests.
"""
from __future__ import annotations

from uuid import uuid4

from app.services.exposure_engine import (
    TELEMETRY_EA,
    TELEMETRY_NETWORK,
    TELEMETRY_CLOUD,
    _aggregate,
    _eval_predicate,
    _Predicate,
    _TenantSnapshot,
)


def _snap(**over) -> _TenantSnapshot:
    defaults = dict(
        tenant_id=uuid4(),
        industry=None,
        systems=[],
        recent_domains={},
        provider_countries=set(),
        integrations_active=set(),
        oauth_grant_app_ids=set(),
        cloud_ai_resources=[],
        aisia_statuses=set(),
        have_ea=False,
    )
    defaults.update(over)
    return _TenantSnapshot(**defaults)


# ---------------------------------------------------------------------------
# Predicate dispatcher
# ---------------------------------------------------------------------------

def test_any_system_category_in_matches() -> None:
    snap = _snap(systems=[{"id": uuid4(), "name": "Cursor",
                            "category": "code_ai", "data_types_processed": [],
                            "eu_ai_act_category": None, "capabilities": [],
                            "aisia_status": None, "current_risk_score": None,
                            "provider_slug": None, "provider_hq": None}])
    r = _eval_predicate("any_system_category_in", ["code_ai"], snap)
    assert r.satisfied is True
    assert "Cursor" in r.detail


def test_any_system_category_in_no_match() -> None:
    r = _eval_predicate("any_system_category_in", ["code_ai"], _snap())
    assert r.satisfied is False


def test_observed_provider_domains_hit() -> None:
    snap = _snap(recent_domains={"api.openai.com": 42})
    r = _eval_predicate("observed_provider_domains", ["api.openai.com"], snap)
    assert r.satisfied is True
    assert "api.openai.com=42" in r.detail


def test_observed_provider_domains_unknown_when_no_telemetry() -> None:
    """Empty recent_domains → predicate is UNKNOWN, not FALSE."""
    r = _eval_predicate("observed_provider_domains", ["api.openai.com"], _snap())
    assert r.satisfied is None
    assert r.needs == TELEMETRY_NETWORK


def test_observed_provider_domains_negative_when_other_domains_seen() -> None:
    snap = _snap(recent_domains={"intranet.bank.local": 100})
    r = _eval_predicate("observed_provider_domains", ["api.openai.com"], snap)
    assert r.satisfied is False


def test_observed_provider_jurisdiction_match() -> None:
    snap = _snap(provider_countries={"CN", "IN"})
    r = _eval_predicate("observed_provider_jurisdiction", ["CN", "RU"], snap)
    assert r.satisfied is True


def test_observed_provider_jurisdiction_no_data_unknown() -> None:
    r = _eval_predicate("observed_provider_jurisdiction", ["CN"], _snap())
    assert r.satisfied is None


def test_endpoint_predicate_unknown_without_ea() -> None:
    r = _eval_predicate("endpoint_agent_curl_pipe_sh_within_days", 30, _snap())
    assert r.satisfied is None
    assert r.needs == TELEMETRY_EA


def test_endpoint_predicate_false_when_ea_active_no_events() -> None:
    r = _eval_predicate(
        "endpoint_agent_curl_pipe_sh_within_days",
        30,
        _snap(have_ea=True, integrations_active={"aegis_endpoint_agent"}),
    )
    assert r.satisfied is False


def test_cloud_predicates_unknown_without_inventory() -> None:
    r1 = _eval_predicate("cloud_ai_resource_without_guardrail", True, _snap())
    assert r1.satisfied is None
    assert r1.needs == TELEMETRY_CLOUD
    r2 = _eval_predicate("cloud_ai_role_wildcard_detected", True, _snap())
    assert r2.satisfied is None


def test_unsupported_predicate_unknown() -> None:
    r = _eval_predicate("future_predicate_we_haven_t_seen_yet", "value", _snap())
    assert r.satisfied is None
    assert r.needs == "engine_update"


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def _p(name: str, satisfied: bool | None, needs: str | None = None) -> _Predicate:
    return _Predicate(name=name, satisfied=satisfied, detail="x", evidence=[], needs=needs)


def test_aggregate_all_satisfied_exposed() -> None:
    e = _aggregate([_p("a", True), _p("b", True)])
    assert e.status == "exposed"
    assert e.missing_telemetry == []


def test_aggregate_any_unknown_blocks_exposed() -> None:
    """One unknown predicate must NOT produce an `exposed` verdict —
    even when another predicate is satisfied — because we cannot
    assert exposure when we lacked the data to verify."""
    e = _aggregate([_p("a", True), _p("b", None, needs="endpoint_agent")])
    assert e.status == "unknown"
    assert "endpoint_agent" in e.missing_telemetry


def test_aggregate_all_false_not_exposed() -> None:
    e = _aggregate([_p("a", False), _p("b", False)])
    assert e.status == "not_exposed"


def test_aggregate_unknown_alone_unknown() -> None:
    e = _aggregate([_p("a", None, needs="cloud_inventory")])
    assert e.status == "unknown"
    assert e.missing_telemetry == ["cloud_inventory"]


def test_aggregate_reasons_show_verdict_prefix() -> None:
    e = _aggregate([_p("foo", True), _p("bar", False), _p("baz", None, needs="x")])
    assert any("PASSED" in r for r in e.reasons)
    assert any("FAILED" in r for r in e.reasons)
    assert any("UNKNOWN" in r for r in e.reasons)
