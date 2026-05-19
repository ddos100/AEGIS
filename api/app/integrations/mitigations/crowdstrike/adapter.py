"""CrowdStrike Falcon mitigation adapter (Phase 7.5+).

Real-mode uses the Falcon API:

  POST /policy/entities/ioa-rule-groups/v1  — IOA rule group
  POST /policy/entities/ioa-rules/v1        — individual IOA rule
  PATCH /policy/entities/ioa-rule-groups/v1 — assign to policy
  POST /policy/entities/ioa-rule-groups-actions/v1 — enable

Service-account OAuth2 client credentials. Dry-run locked at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Falcon IOA rule groups + assignments"


@register(integration="crowdstrike", action="ioa_rule")
class CrowdStrikeIOA(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="CS-IOA", required=["ioa_id"], params=params,
            detail_tmpl="would create + enable CrowdStrike Falcon IOA rule "
                         "{ioa_id!r} against the default Prevention policy",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
