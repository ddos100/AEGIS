"""Entra ID (Azure AD) mitigation adapters (Phase 7.5+).

Real-mode uses Microsoft Graph API:

  DELETE /v1.0/oauth2PermissionGrants/{id}
  DELETE /v1.0/servicePrincipals/{id}/appRoleAssignments/{id}
  PATCH  /v1.0/servicePrincipals/{id}  (accountEnabled=false)

Revokes OAuth2 grants for shadow AI applications discovered via the
Entra ID scanner (Phase 3).  Service principal w/ Application.ReadWrite.All.
Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Entra ID OAuth2 permission grants"


@register(integration="entra_id", action="oauth_grant_revoke")
class EntraIDOAuthGrantRevoke(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="ENTRA-OAR",
            required=["grant_id"],
            params=params,
            detail_tmpl="would revoke Entra ID OAuth2 permission grant {grant_id!r} "
                        "for the shadow AI application via Graph API DELETE",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
