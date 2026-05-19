"""M365 Copilot mitigation adapters (Phase 7.5+).

Real-mode uses Microsoft Graph API + Purview sensitivity labels:

  PATCH /beta/admin/microsoft365Apps/settings
  POST  /beta/security/informationProtection/sensitivityLabels
  POST  /beta/security/labels/retentionLabels

Restricts Copilot data grounding via sensitivity labels on SharePoint
sites and containers.  Service principal w/ Information Protection Admin.
Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "M365 Copilot sensitivity label restrictions"


@register(integration="m365_copilot", action="restrict_via_sensitivity_labels")
class M365CopilotRestrictViaSensitivityLabels(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="M365-COP",
            required=["label_name", "scope"],
            params=params,
            detail_tmpl="would apply sensitivity label {label_name!r} to scope "
                        "{scope!r} to restrict M365 Copilot data grounding on "
                        "labelled SharePoint sites and containers",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
