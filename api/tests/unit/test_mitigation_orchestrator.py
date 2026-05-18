"""Orchestrator helper logic — pure-Python tests.

The DB-touching `propose_for_exposure` / `propose_all` are exercised in
the compose-based e2e tests. Here we lock down the idempotency-key
contract that the orchestrator relies on for deterministic upserts.
"""
from __future__ import annotations

from uuid import UUID

from app.services.mitigation_orchestrator import (
    TERMINAL_STATES,
    _canonical_params,
    _idempotency_key,
)


def test_canonical_params_sorted_keys() -> None:
    a = {"a": 1, "b": 2}
    b = {"b": 2, "a": 1}
    assert _canonical_params(a) == _canonical_params(b)
    # None and empty dict are distinct strings (forward-compat)
    assert _canonical_params(None) == "null"
    assert _canonical_params({}) == "{}"


def test_idempotency_key_stable_for_same_inputs() -> None:
    t = UUID("00000000-0000-0000-0000-000000000001")
    th = UUID("00000000-0000-0000-0000-000000000002")
    k1 = _idempotency_key(t, th, "zscaler", "block_url_category", {"category": "X"})
    k2 = _idempotency_key(t, th, "zscaler", "block_url_category", {"category": "X"})
    assert k1 == k2


def test_idempotency_key_changes_on_param_diff() -> None:
    t = UUID("00000000-0000-0000-0000-000000000001")
    th = UUID("00000000-0000-0000-0000-000000000002")
    k1 = _idempotency_key(t, th, "zscaler", "block_url_category", {"category": "X"})
    k2 = _idempotency_key(t, th, "zscaler", "block_url_category", {"category": "Y"})
    assert k1 != k2


def test_idempotency_key_changes_on_integration_diff() -> None:
    t = UUID("00000000-0000-0000-0000-000000000001")
    th = UUID("00000000-0000-0000-0000-000000000002")
    k1 = _idempotency_key(t, th, "zscaler",   "block_url_category", {"c": "X"})
    k2 = _idempotency_key(t, th, "paloalto",  "block_url_category", {"c": "X"})
    assert k1 != k2


def test_idempotency_key_changes_on_tenant_diff() -> None:
    th = UUID("00000000-0000-0000-0000-000000000002")
    a  = UUID("00000000-0000-0000-0000-00000000000a")
    b  = UUID("00000000-0000-0000-0000-00000000000b")
    k1 = _idempotency_key(a, th, "zscaler", "x", {})
    k2 = _idempotency_key(b, th, "zscaler", "x", {})
    assert k1 != k2


def test_terminal_states_contract() -> None:
    """The orchestrator must NEVER overwrite a row in these states."""
    expected = {"rejected", "dismissed", "applied", "verified", "rolled_back", "failed"}
    assert TERMINAL_STATES == expected
