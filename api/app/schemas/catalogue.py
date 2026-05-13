"""Pydantic schemas for the AI Service Catalogue."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIServiceBrief(BaseModel):
    """Minimal catalogue entry — used in list views and quick-add."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    catalogue_id: str
    name: str
    provider_slug: str | None
    category: str
    subcategory: str | None
    description: str | None
    eu_ai_act_cat: str | None
    tags: list[str] = Field(default_factory=list)


class AIServiceDetail(AIServiceBrief):
    """Full catalogue entry."""
    website: str | None
    api_patterns: list[str] = Field(default_factory=list)
    browser_domains: list[str] = Field(default_factory=list)
    entra_app_ids: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    hq_country: str | None
    gdpr_applicable: bool
    risk_hints: dict = Field(default_factory=dict)
    catalogue_version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryStat(BaseModel):
    category: str
    count: int


class ProviderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    hq_country: str | None
    trust_score: int | None
    soc2_certified: bool
    iso27001_cert: bool
    gdpr_dpa: bool
