"""Sophos XDR mitigation adapter (Phase 7.5+).

Real-mode uses Sophos Central API + Live Response:

  POST /endpoint/v1/endpoints/{id}/isolation       — endpoint isolation
  POST /live-discover/v1/queries/runs              — schedule a query
  POST /live-response/v1/sessions                  — open Live Response
  POST /endpoint/v1/scans                          — initiate scan

Sophos Central OAuth2. Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Sophos Central endpoint policies + Live Response"


@register(integration="sophos_xdr", action="live_response_block")
class SophosXDRLiveResponseBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="SXDR-LR", required=["rule_ref"], params=params,
            detail_tmpl="would push Sophos Central runtime block rule "
                         "{rule_ref!r} via Live Response to the default device group",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
