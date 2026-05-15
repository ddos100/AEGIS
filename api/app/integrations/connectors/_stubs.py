"""Placeholder connectors for vendors whose full implementation lands in
a later iteration. Registers the integration key so the API surfaces it
in /v1/integrations/types — operators see a clear "not yet implemented"
error if they try to sync.

Each stub is intentionally trivial. Replace with a vendor/ package +
connector.py once the real implementation is ready.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.integrations.connectors.base import BaseConnector, SyncResult, register_connector


@register_connector("azure", kind="cloud")
class AzureConnectorStub(BaseConnector):
    """Azure AI inventory — Azure OpenAI + Cognitive Services + ML workspaces.

    Stub: full implementation pending. Will use the azure-mgmt-resource +
    azure-identity SDKs to enumerate Microsoft.CognitiveServices/accounts and
    Microsoft.MachineLearningServices/workspaces.
    """
    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        return SyncResult(ok=False, error="azure connector not yet implemented (Phase 3 follow-up)")

    async def sync(self, credentials, *, tenant_id, integration_id, session) -> SyncResult:
        return SyncResult(ok=False, error="azure connector not yet implemented")


@register_connector("gcp", kind="cloud")
class GcpConnectorStub(BaseConnector):
    """GCP Vertex AI + Cloud AI APIs.

    Stub: full implementation pending. Will use google-cloud-asset +
    google-cloud-aiplatform SDKs.
    """
    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        return SyncResult(ok=False, error="gcp connector not yet implemented (Phase 3 follow-up)")

    async def sync(self, credentials, *, tenant_id, integration_id, session) -> SyncResult:
        return SyncResult(ok=False, error="gcp connector not yet implemented")


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
