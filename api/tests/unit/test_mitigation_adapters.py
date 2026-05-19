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


# Complete list of expected (integration, action) pairs across all 18 adapters.
EXPECTED_PAIRS: set[tuple[str, str]] = {
    # Network / proxy / DNS
    ("zscaler", "block_url_category"),
    ("zscaler", "rate_limit_url"),
    ("cisco_umbrella", "domain_destination_list"),
    ("cisco_umbrella", "domain_destination_list_by_country"),
    ("cloudflare_gateway", "block_dns_category"),
    ("cloudflare_gateway", "block_url"),
    # NGFW / XDR / EDR
    ("palo_alto", "block_url_category"),
    ("palo_alto", "block_url_category_by_provider_country"),
    ("palo_alto", "block_url_category_by_data_class"),
    ("palo_alto", "block_url_category_for_department"),
    ("crowdstrike", "ioa_rule"),
    ("sentinelone", "storyline_block"),
    ("sophos_xdr", "live_response_block"),
    # Browser / endpoint management
    ("chrome_enterprise", "extension_install_blocklist"),
    ("chrome_enterprise", "ide_extension_install_blocklist"),
    # Microsoft 365 / Purview
    ("microsoft_purview_dlp", "sensitive_info_type_policy"),
    ("microsoft_purview_dlp", "scan_ingest_sources"),
    ("m365_copilot", "restrict_via_sensitivity_labels"),
    # Identity providers
    ("entra_id", "oauth_grant_revoke"),
    ("okta", "oauth_app_deactivate"),
    # Cloud platforms
    ("aws", "scope_iam_role_to_least_privilege"),
    ("aws_bedrock", "attach_guardrail"),
    ("aws_bedrock", "provisioned_throughput_cap"),
    ("azure", "scope_role_to_least_privilege"),
    ("azure_openai", "enable_content_safety"),
    # AEGIS-native
    ("aegis_endpoint_agent", "curl_pipe_sh_block"),
    ("aegis_endpoint_agent", "package_install_pre_hook_block"),
    ("aegis_endpoint_agent", "secret_path_read_block"),
    ("aegis_endpoint_agent", "mcp_config_policy_warn"),
    ("aegis_endpoint_agent", "destructive_cmd_block_under_ai_proc"),
    ("aegis_endpoint_agent", "git_push_pre_hook_block"),
    ("aegis_endpoint_agent", "docker_privileged_block_under_ai_proc"),
    ("aegis_endpoint_agent", "npm_postinstall_block"),
    ("aegis_endpoint_agent", "shell_rc_write_block"),
    ("aegis_endpoint_agent", "suid_bit_strip"),
    ("aegis_endpoint_agent", "chmod_secret_files"),
    ("aegis_endpoint_agent", "model_hash_allowlist_enforce"),
    ("aegis_policy_engine", "require_aisia_completion"),
    ("aegis_policy_engine", "require_risk_recompute"),
}


def test_adapter_inventory_complete() -> None:
    """Every documented adapter must be registered and flagged dry-run."""
    inv = list_adapters()
    pairs = {(a["integration"], a["action"]) for a in inv}
    missing = EXPECTED_PAIRS - pairs
    assert not missing, f"Missing adapter registrations: {missing}"
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


# ── Parametrized round-trip tests for all adapters ──────────────────────
# Each tuple: (integration, action, params_dict, expected_prefix)
_ROUND_TRIP_CASES = [
    # NGFW / XDR / EDR
    ("palo_alto", "block_url_category", {"category": "AI Chat"}, "PAN-CAT-"),
    ("palo_alto", "block_url_category_by_provider_country", {"country_denylist": ["CN", "RU"]}, "PAN-CAT-CC-"),
    ("palo_alto", "block_url_category_by_data_class", {"category": "AI Chat"}, "PAN-CAT-DC-"),
    ("palo_alto", "block_url_category_for_department", {"category": "AI Chat"}, "PAN-CAT-DEPT-"),
    ("crowdstrike", "ioa_rule", {"ioa_id": "CS-123"}, "CS-IOA-"),
    ("sentinelone", "storyline_block", {"story_ref": "S1-789"}, "S1-SL-"),
    ("sophos_xdr", "live_response_block", {"rule_ref": "SX-001"}, "SXDR-LR-"),
    # Chrome
    ("chrome_enterprise", "extension_install_blocklist", {"extension_id": "abcdefgh"}, "CBCM-EXT-"),
    ("chrome_enterprise", "ide_extension_install_blocklist", {"extension_id": "ijklmnop"}, "CBCM-IDE-"),
    # Microsoft
    ("microsoft_purview_dlp", "sensitive_info_type_policy", {"sit_name": "AI Output", "action": "block"}, "PURV-SIT-"),
    ("microsoft_purview_dlp", "scan_ingest_sources", {"scan_scope": "exchange,spo"}, "PURV-SCAN-"),
    ("m365_copilot", "restrict_via_sensitivity_labels", {"label_name": "Confidential", "scope": "site://hr"}, "M365-COP-"),
    # IdP
    ("entra_id", "oauth_grant_revoke", {"grant_id": "grant-abc"}, "ENTRA-OAR-"),
    ("okta", "oauth_app_deactivate", {"app_id": "0oa1234"}, "OKTA-APP-"),
    # Cloud
    ("aws", "scope_iam_role_to_least_privilege", {"role_name": "ai-dev", "denied_services": ["bedrock:*"]}, "AWS-IAM-"),
    ("aws_bedrock", "attach_guardrail", {"guardrail_name": "pii-filter", "model_id": "anthropic.claude-3"}, "BDR-GR-"),
    ("aws_bedrock", "provisioned_throughput_cap", {"model_id": "anthropic.claude-3", "max_model_units": 5}, "BDR-CAP-"),
    ("azure", "scope_role_to_least_privilege", {"principal_id": "sp-123", "denied_actions": ["Microsoft.CognitiveServices/*"]}, "AZ-RBAC-"),
    ("azure_openai", "enable_content_safety", {"deployment_name": "gpt4-prod", "filter_severity": "medium"}, "AOAI-CS-"),
    # AEGIS EA (all 12)
    ("aegis_endpoint_agent", "curl_pipe_sh_block", {"enforcement": "block"}, "EA-CPSH-"),
    ("aegis_endpoint_agent", "package_install_pre_hook_block", {"enforcement": "warn"}, "EA-PIHK-"),
    ("aegis_endpoint_agent", "secret_path_read_block", {"enforcement": "block"}, "EA-SECR-"),
    ("aegis_endpoint_agent", "mcp_config_policy_warn", {"enforcement": "warn"}, "EA-MCP-"),
    ("aegis_endpoint_agent", "destructive_cmd_block_under_ai_proc", {"enforcement": "block"}, "EA-DCMD-"),
    ("aegis_endpoint_agent", "git_push_pre_hook_block", {"enforcement": "audit"}, "EA-GPSH-"),
    ("aegis_endpoint_agent", "docker_privileged_block_under_ai_proc", {"enforcement": "block"}, "EA-DPRV-"),
    ("aegis_endpoint_agent", "npm_postinstall_block", {"enforcement": "warn"}, "EA-NPMI-"),
    ("aegis_endpoint_agent", "shell_rc_write_block", {"enforcement": "block"}, "EA-SHRC-"),
    ("aegis_endpoint_agent", "suid_bit_strip", {"enforcement": "block"}, "EA-SUID-"),
    ("aegis_endpoint_agent", "chmod_secret_files", {"enforcement": "warn"}, "EA-CHSC-"),
    ("aegis_endpoint_agent", "model_hash_allowlist_enforce", {"enforcement": "block"}, "EA-MDLH-"),
    # AEGIS policy engine
    ("aegis_policy_engine", "require_aisia_completion", {"ai_system_id": "sys-001"}, "POL-AISIA-"),
    ("aegis_policy_engine", "require_risk_recompute", {"ai_system_id": "sys-002"}, "POL-RISK-"),
]


@pytest.mark.parametrize("integration,action,params,prefix", _ROUND_TRIP_CASES,
                         ids=[f"{i}-{a}" for i, a, _, _ in _ROUND_TRIP_CASES])
def test_adapter_apply_verify_rollback_round_trip(
    integration: str, action: str, params: dict, prefix: str,
) -> None:
    """Full dry-run lifecycle: apply → verify → rollback for every adapter."""
    adapter = get_adapter(integration, action)

    # --- apply ---
    apply_r = asyncio.run(adapter.apply(credentials=None, params=params))
    assert isinstance(apply_r, MitigationApplyResult)
    assert apply_r.ok is True
    assert apply_r.dry_run is True
    assert apply_r.vendor_ref and apply_r.vendor_ref.startswith(prefix)
    assert apply_r.state_blob is not None

    # --- verify ---
    verify_r = asyncio.run(adapter.verify(
        credentials=None, params=params, state_blob=apply_r.state_blob,
    ))
    assert isinstance(verify_r, MitigationVerifyResult)
    assert verify_r.verified is True
    assert verify_r.dry_run is True
    assert apply_r.vendor_ref in verify_r.detail

    # --- rollback ---
    rollback_r = asyncio.run(adapter.rollback(
        credentials=None, params=params, state_blob=apply_r.state_blob,
    ))
    assert isinstance(rollback_r, MitigationApplyResult)
    assert rollback_r.ok is True
    assert rollback_r.dry_run is True


@pytest.mark.parametrize("integration,action,params,prefix", _ROUND_TRIP_CASES,
                         ids=[f"{i}-{a}-missing" for i, a, _, _ in _ROUND_TRIP_CASES])
def test_adapter_apply_rejects_empty_params(
    integration: str, action: str, params: dict, prefix: str,
) -> None:
    """Every adapter must reject an empty params dict."""
    adapter = get_adapter(integration, action)
    r = asyncio.run(adapter.apply(credentials=None, params={}))
    assert r.ok is False
    assert "Missing required" in (r.error or "")


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
