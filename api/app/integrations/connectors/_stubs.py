"""Placeholder connectors for vendors whose full implementation lands in
a later iteration. Registers the integration key so the API surfaces it
in /v1/integrations/types — operators see a clear "not yet implemented"
error if they try to sync.

After the Phase 5 hardening pass:
  - azure  → now a real implementation in app.integrations.connectors.azure
  - gcp    → now a real implementation in app.integrations.connectors.gcp

google_workspace remains a stub.
"""
from __future__ import annotations

from typing import Any

from app.integrations.connectors.base import BaseConnector, SyncResult, register_connector


@register_connector("google_workspace", kind="idp")
class GoogleWorkspaceStub(BaseConnector):
    """Google Workspace — OAuth token grants via Admin SDK.

    Stub: pending. Will pull from
    https://admin.googleapis.com/admin/directory/v1/tokens.
    """
    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        return SyncResult(ok=False, error="google_workspace connector not yet implemented")

    async def sync(self, credentials, *, tenant_id, integration_id, session) -> SyncResult:
        return SyncResult(ok=False, error="google_workspace connector not yet implemented")
