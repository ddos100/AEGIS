"""Pydantic payloads for the discovery ingest + extension endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- network / xdr ingest ----------

class IngestBatch(BaseModel):
    """Single batch of raw log records from any registered source."""
    source: str = Field(..., description="Registered normalizer source key, e.g. 'zscaler_nss'")
    tenant_id: UUID = Field(..., description="Target tenant. The ingest API key is shared, so the "
                                              "tenant is identified inside the payload.")
    batch_id: str | None = None
    events: list[Any] = Field(..., min_length=1, max_length=10_000)


class IngestResponse(BaseModel):
    accepted: int
    queued: bool
    matched: int | None = None
    shadow_new: int | None = None


# ---------- extension ----------

class ExtensionEnrollRequest(BaseModel):
    device_fingerprint: str = Field(..., min_length=8, max_length=128)
    user_email: str | None = None
    hostname: str | None = None
    browser_version: str | None = None
    extension_version: str
    os_platform: str | None = None


class ExtensionEnrollResponse(BaseModel):
    device_id: UUID
    catalogue_version: str = Field(..., description="Opaque hash; force a refresh when it changes.")


class ExtensionEvent(BaseModel):
    type: str  # ai_web_app_visit | ai_extension_detected | ai_extension_dom_detected
    catalogue_id: str | None = None
    domain: str | None = None
    extension_id: str | None = None
    occurred_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)


class ExtensionEventBatch(BaseModel):
    device_id: UUID
    tenant_id: UUID
    events: list[ExtensionEvent] = Field(..., min_length=1, max_length=200)


class ExtensionCatalogueResponse(BaseModel):
    version: str
    domains: dict[str, str]      # domain -> catalogue_id
    extensions: dict[str, str]   # chrome extension id -> catalogue_id


# ---------- discovery feed ----------

class DiscoveryFeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    occurred_at: datetime
    catalogue_slug: str | None
    ai_system_id: UUID | None
    name: str | None
    category: str | None
    vector: str
    source: str
    user_email: str | None
    department: str | None
    is_new: bool


class UsageSummaryRow(BaseModel):
    bucket: datetime
    catalogue_slug: str | None
    ai_system_id: UUID | None
    vector: str
    event_count: int
    unique_users: int


class MatcherStats(BaseModel):
    ac_patterns: int
    process_patterns: int
    sources: dict[str, dict[str, str]]
