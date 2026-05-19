"""Chrome Enterprise CBCM mitigation adapters (Phase 7.5+).

Real-mode uses Chrome Browser Cloud Management API:

  POST /admin/directory/v1.1/customer/{id}/devices/chromebrowsers/moveChromeBrowsersToOU
  PUT  /admin/directory/v1.1/customer/{id}/devices/chromebrowsers/{deviceId}
  PATCH /chrome/policy/v1/customers/{id}/policies/orgunits:batchModify

Manages extension install blocklists and IDE extension blocking via
Chrome policy OrgUnits.  OAuth2 service account w/ Chrome CBCM scopes.
Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Chrome Browser Cloud Management policies"


@register(integration="chrome_enterprise", action="extension_install_blocklist")
class ChromeExtensionInstallBlocklist(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="CBCM-EXT",
            required=["extension_id"],
            params=params,
            detail_tmpl="would add Chrome extension {extension_id!r} to the "
                        "ExtensionInstallBlocklist policy for the target OU",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="chrome_enterprise", action="ide_extension_install_blocklist")
class ChromeIDEExtensionBlocklist(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="CBCM-IDE",
            required=["extension_id"],
            params=params,
            detail_tmpl="would add IDE extension {extension_id!r} (VS Code / Cursor / "
                        "Windsurf marketplace ID) to the managed Chrome policy blocklist",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
