"""Okta mitigation adapters (Phase 7.5+).

Real-mode uses Okta Apps API:

  POST /api/v1/apps/{appId}/lifecycle/deactivate
  DELETE /api/v1/apps/{appId}/grants/{grantId}
  DELETE /api/v1/apps/{appId}/tokens/{tokenId}

Deactivates OAuth apps (shadow AI) discovered via Okta scanner.
Okta API token w/ okta.apps.manage scope.  Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Okta application lifecycle"


@register(integration="okta", action="oauth_app_deactivate")
class OktaOAuthAppDeactivate(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="OKTA-APP",
            required=["app_id"],
            params=params,
            detail_tmpl="would deactivate Okta OAuth application {app_id!r} via "
                        "POST /api/v1/apps/{app_id}/lifecycle/deactivate",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
