"""AWS IAM mitigation adapters (Phase 7.5+).

Real-mode uses AWS IAM + STS APIs:

  iam:PutRolePermissionsBoundary
  iam:AttachRolePolicy  (deny policy for AI services)
  iam:CreatePolicy       (scoped deny for bedrock:*, sagemaker:*, etc.)

Scopes IAM roles to least privilege by attaching a deny policy boundary
that blocks access to AI services not in the approved registry.
AssumeRole w/ iam:PutRolePermissionsBoundary.  Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "AWS IAM permission boundaries"


@register(integration="aws", action="scope_iam_role_to_least_privilege")
class AWSScopeIAMRole(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="AWS-IAM",
            required=["role_name", "denied_services"],
            params=params,
            detail_tmpl="would attach IAM permissions boundary to role {role_name!r} "
                        "denying {denied_services!r} (AI services not in approved registry)",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
