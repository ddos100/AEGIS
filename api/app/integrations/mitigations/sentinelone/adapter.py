"""SentinelOne Singularity mitigation adapter (Phase 7.5+).

Real-mode uses the Management API:

  POST /web/api/v2.1/threats/blacklist           — threat blocklist
  POST /web/api/v2.1/threats/storyline/{id}/mark — mark Storyline as bad
  PATCH /web/api/v2.1/policies/{id}              — adjust policy

API-token auth. Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "SentinelOne Storyline blocklist + policy"


@register(integration="sentinelone", action="storyline_block")
class SentinelOneStorylineBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="S1-SL", required=["story_ref"], params=params,
            detail_tmpl="would add SentinelOne Storyline rule {story_ref!r} "
                         "to the threat blocklist on the default site",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
