"""Microsoft Purview DLP mitigation adapters (Phase 7.5+).

Real-mode uses Microsoft Graph Security & Compliance API:

  POST /beta/security/informationProtection/sensitivityLabels
  POST /beta/security/dataLossPreventionPolicies
  POST /beta/security/triggers/retentionEvents

Creates Sensitive Information Type (SIT) DLP policies and triggers
content scanning across Exchange, SharePoint, OneDrive, and Teams.
Service principal w/ Compliance Administrator role.  Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Microsoft Purview DLP policies"


@register(integration="microsoft_purview_dlp", action="sensitive_info_type_policy")
class PurviewSensitiveInfoTypePolicy(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PURV-SIT",
            required=["sit_name", "action"],
            params=params,
            detail_tmpl="would create Purview DLP policy for Sensitive Info Type "
                        "{sit_name!r} with action={action!r} across Exchange/SPO/Teams",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="microsoft_purview_dlp", action="scan_ingest_sources")
class PurviewScanIngestSources(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PURV-SCAN",
            required=["scan_scope"],
            params=params,
            detail_tmpl="would trigger Purview compliance scan on scope {scan_scope!r} "
                        "to detect AI-generated content or sensitive data leakage",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
