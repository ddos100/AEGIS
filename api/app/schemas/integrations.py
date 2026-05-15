"""Pydantic payloads for Phase 3 integrations + cloud/IdP discovery views."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- integration_credentials ----------

class IntegrationCreate(BaseModel):
    integration: str = Field(..., description="entra_id | okta | aws | azure | gcp | m365_copilot | google_workspace")
    name: str = Field(..., min_length=1, max_length=255)
    credentials: dict[str, Any] = Field(..., description="Vendor-specific cleartext credentials; encrypted at rest")
    scopes: list[str] = Field(default_factory=list)


class IntegrationUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    credentials: dict[str, Any] | None = None
    scopes: list[str] | None = None


class IntegrationBrief(BaseModel):
    """Safe public view — never includes the credential ciphertext."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration: str
    kind: str
    name: str
    status: str
    scopes: list[str] = Field(default_factory=list)
    last_used_at: datetime | None
    last_sync_at: datetime | None
    last_sync_result: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ConnectorInfo(BaseModel):
    integration: str
    kind: str
    cls: str
    doc: str


class SyncRunResponse(BaseModel):
    ok: bool
    discovered_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------- oauth_grants ----------

class OAuthGrantRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    app_id: str
    app_name: str
    app_publisher: str | None
    granted_scopes: list[str] = Field(default_factory=list)
    consent_type: str | None
    catalogue_match: UUID | None
    ai_system_id: UUID | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_revoked: bool


# ---------- cloud_ai_resources ----------

class CloudResourceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    cloud_provider: str
    resource_type: str
    resource_id: str
    resource_name: str | None
    region: str | None
    account_id: str | None
    project_id: str | None
    service_name: str | None
    model_id: str | None
    status: str | None
    catalogue_match: UUID | None
    ai_system_id: UUID | None
    first_seen_at: datetime
    last_scanned_at: datetime
