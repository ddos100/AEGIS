"""Pydantic schemas for the AI System Registry."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# -------- enums (kept as Literal-style strings to mirror the DB-stored values) --------

CATEGORIES = (
    "llm", "image_gen", "video_gen", "speech", "code", "search", "recommendation",
    "classifier", "embedding", "agent", "browser_extension", "security_ai",
    "data_analytics", "other",
)
DEPLOYMENT_TYPES = (
    "cloud_saas", "cloud_api", "on_premise", "browser_extension",
    "desktop_agent", "embedded_saas",
)
STATUSES = ("active", "pilot", "decommissioned", "under_review")
AISIA_STATUSES = ("not_started", "in_progress", "completed", "requires_review")
POLICY_STATUSES = ("allow", "monitor", "alert", "block", "requires_approval")
DATA_TYPES = (
    "personal", "sensitive_personal", "financial", "health", "biometric",
    "internal", "public", "intellectual_property", "credentials", "other",
)
DATA_SUBJECTS = ("employees", "customers", "third_parties", "public", "minors", "other")
OUTPUT_TYPES = (
    "decision", "recommendation", "content_generation", "classification",
    "prediction", "summary", "translation", "other",
)
DISCOVERY_VECTORS = (
    "network_telemetry", "browser_ext", "endpoint", "idp", "cloud",
    "saas", "code_repo", "xdr_edr", "manual",
)


# -------- request / response models --------

class AISystemBase(BaseModel):
    """Fields shared by create and update payloads."""

    name: str = Field(..., min_length=1, max_length=255)
    internal_alias: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=64)
    catalogue_service_id: UUID | None = None
    provider_id: UUID | None = None
    provider_name_freetext: str | None = Field(default=None, max_length=255)

    category: str = Field(..., description="Must be one of CATEGORIES")
    subcategory: str | None = Field(default=None, max_length=120)
    deployment_type: str = "cloud_saas"
    deployment_env: str = "production"

    intended_purpose: str | None = None
    actual_use_observed: str | None = None
    user_population: str | None = Field(default=None, max_length=255)
    affected_data_subjects: list[str] = Field(default_factory=list)
    data_types_processed: list[str] = Field(default_factory=list)
    output_type: str | None = None
    human_oversight_desc: str | None = None
    geographic_scope: list[str] = Field(default_factory=list)

    owner_user_id: UUID | None = None
    department_id: UUID | None = None
    business_unit: str | None = Field(default=None, max_length=120)

    status: str = "active"
    first_deployed_at: date | None = None
    decommission_date: date | None = None

    aisia_status: str = "not_started"
    eu_ai_act_category: str | None = None

    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AISystemCreate(AISystemBase):
    pass


class AISystemUpdate(BaseModel):
    """All-optional partial update payload (PATCH)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    internal_alias: str | None = None
    version: str | None = None
    catalogue_service_id: UUID | None = None
    provider_id: UUID | None = None
    provider_name_freetext: str | None = None

    category: str | None = None
    subcategory: str | None = None
    deployment_type: str | None = None
    deployment_env: str | None = None

    intended_purpose: str | None = None
    actual_use_observed: str | None = None
    user_population: str | None = None
    affected_data_subjects: list[str] | None = None
    data_types_processed: list[str] | None = None
    output_type: str | None = None
    human_oversight_desc: str | None = None
    geographic_scope: list[str] | None = None

    owner_user_id: UUID | None = None
    department_id: UUID | None = None
    business_unit: str | None = None

    status: str | None = None
    first_deployed_at: date | None = None
    decommission_date: date | None = None

    aisia_status: str | None = None
    eu_ai_act_category: str | None = None
    policy_status: str | None = None

    notes: str | None = None
    tags: list[str] | None = None
    custom_fields: dict[str, Any] | None = None


class AISystemListItem(BaseModel):
    """Compact row for the Registry list view."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider_slug: str | None = None
    category: str
    subcategory: str | None
    deployment_type: str
    status: str
    risk_level: str | None
    current_risk_score: int | None
    policy_status: str
    completeness_score: int
    is_shadow: bool
    aisia_status: str
    discovery_sources: list[str] = Field(default_factory=list)
    department_id: UUID | None
    owner_user_id: UUID | None
    last_seen_at: datetime | None
    created_at: datetime


class AISystemDetail(AISystemBase):
    """Full registry record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    discovery_sources: list[str] = Field(default_factory=list)
    first_discovered_at: datetime | None
    last_seen_at: datetime | None
    is_shadow: bool
    current_risk_score: int | None
    risk_level: str | None
    last_risk_assessed_at: datetime | None
    aisia_impact_level: str | None
    policy_status: str
    compliance_flags: dict[str, Any] = Field(default_factory=dict)
    completeness_score: int
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    updated_by: UUID | None


class RegistryStats(BaseModel):
    total: int
    shadow_count: int
    completeness_avg: float
    by_risk_level: dict[str, int]
    by_category: dict[str, int]
    by_status: dict[str, int]
    aisia_pending_count: int


class FromCatalogueRequest(BaseModel):
    catalogue_service_id: UUID
    department_id: UUID | None = None
    owner_user_id: UUID | None = None
    deployment_type: str | None = None
    intended_purpose: str | None = None
