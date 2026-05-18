"""Mitigation adapter framework + reference adapter tests.

These exercise the in-process registry, dispatcher, and dry-run
contract for the three shipped adapters. No vendor I/O.
"""
from __future__ import annotations

import asyncio

import pytest

from app.integrations.mitigations import (
    BaseMitigationAdapter,
    MitigationApplyResult,
    MitigationVerifyResult,
    get_adapter,
    list_adapters,
    register,
)


def test_adapter_inventory_contains_three_vendors() -> None:
    inv = list_adapters()
    pairs = {(a["integration"], a["action"]) for a in inv}
    assert ("zscaler", "block_url_category") in pairs
    assert ("zscaler", "rate_limit_url") in pairs
    assert ("cisco_umbrella", "domain_destination_list") in pairs
    assert ("cisco_umbrella", "domain_destination_list_by_country") in pairs
    assert ("cloudflare_gateway", "block_dns_category") in pairs
    assert ("cloudflare_gateway", "block_url") in pairs
    # All shipped adapters are dry-run by default per the Phase 7.5 contract.
    for a in inv:
        assert a["dry_run"] is True


def test_unknown_adapter_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("nonexistent_vendor", "nope")


def test_zscaler_block_apply_requires_category() -> None:
    a = get_adapter("zscaler", "block_url_category")
    r = asyncio.run(a.apply(credentials=None, params={}))
    assert isinstance(r, MitigationApplyResult)
    assert r.ok is False
    assert "category" in (r.error or "").lower()


def test_zscaler_block_apply_dry_run_ok() -> None:
    a = get_adapter("zscaler", "block_url_category")
    r = asyncio.run(a.apply(credentials=None,
                              params={"category": "Public AI Chatbots"}))
    assert r.ok is True
    assert r.dry_run is True
    assert r.vendor_ref and r.vendor_ref.startswith("ZIA-CAT-")
    assert r.state_blob.get("category") == "Public AI Chatbots"


def test_cisco_umbrella_verify_round_trips_state_blob() -> None:
    a = get_adapter("cisco_umbrella", "domain_destination_list")
    apply_r = asyncio.run(a.apply(credentials=None,
                                    params={"list_ref": "AEGIS-DL-X"}))
    assert apply_r.ok and apply_r.state_blob["list_ref"] == "AEGIS-DL-X"
    verify_r = asyncio.run(a.verify(credentials=None, params={},
                                      state_blob=apply_r.state_blob))
    assert isinstance(verify_r, MitigationVerifyResult)
    assert verify_r.verified is True
    assert "AEGIS-DL-X" in verify_r.detail


def test_cloudflare_block_url_requires_url_pattern() -> None:
    a = get_adapter("cloudflare_gateway", "block_url")
    r = asyncio.run(a.apply(credentials=None, params={}))
    assert r.ok is False
    assert "url_pattern" in (r.error or "")


def test_cloudflare_block_dns_dry_run_emits_vendor_ref() -> None:
    a = get_adapter("cloudflare_gateway", "block_dns_category")
    r = asyncio.run(a.apply(credentials=None, params={"category": "AI Deepfake Studios"}))
    assert r.ok is True
    assert r.vendor_ref and r.vendor_ref.startswith("CF-GW-")


def test_duplicate_registration_raises() -> None:
    """The decorator guards against accidental double-registration of an
    (integration, action) pair — without that, an adapter override could
    silently mask the original."""
    with pytest.raises(RuntimeError, match="Duplicate adapter"):
        @register(integration="zscaler", action="block_url_category")
        class _Dup(BaseMitigationAdapter):  # type: ignore[unused-ignore]
            async def apply(self, *, credentials, params):
                return MitigationApplyResult(ok=True, dry_run=True)
            async def verify(self, *, credentials, params, state_blob):
                return MitigationVerifyResult(verified=True)
