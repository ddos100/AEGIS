"""Azure RBAC mitigation adapters (Phase 7.5+).

Real-mode uses Azure Resource Manager API:

  PUT /subscriptions/{sub}/providers/Microsoft.Authorization/roleAssignments/{id}
  PUT /subscriptions/{sub}/providers/Microsoft.Authorization/denyAssignments/{id}

Scopes Azure RBAC roles to least privilege by creating deny assignments
that block access to Azure AI services (Cognitive Services, ML workspaces,
Azure OpenAI) not in the approved registry.
Service principal w/ User Access Administrator on subscription.
Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Azure RBAC deny assignments"


@register(integration="azure", action="scope_role_to_least_privilege")
class AzureScopeRole(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="AZ-RBAC",
            required=["principal_id", "denied_actions"],
            params=params,
            detail_tmpl="would create Azure deny assignment for principal {principal_id!r} "
                        "blocking {denied_actions!r} (unapproved AI service actions)",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
