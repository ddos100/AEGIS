"""Pydantic schemas for the Threat catalogue API (Phase 7.1)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThreatBrief(BaseModel):
    """Row shape for the catalogue list endpoint."""
    model_config = ConfigDict(from_attributes=True)

    id:                UUID
    threat_id:         str
    title:             str
    severity:          str
    classes:           list[str]
    vectors:           list[str]
    source_ref:        str
    mitre_atlas_ids:   list[str] = Field(default_factory=list)
    owasp_llm_ids:     list[str] = Field(default_factory=list)
    sector_amplifiers: list[str] = Field(default_factory=list)
    applies_to_jurisdictions: list[str] = Field(default_factory=list)
    catalogue_version: str
    last_updated:      date


class ThreatDetail(ThreatBrief):
    """Full record returned by /v1/threats/{threat_id}."""
    verbatim_description: str
    description:    str | None = None
    exposure_check: dict[str, Any]
    mitigation:     dict[str, Any] | None = None
    evidence_hints: list[str] = Field(default_factory=list)
    compliance_implications: list[str] = Field(default_factory=list)
    created_at:     datetime
    updated_at:     datetime


class ThreatListResponse(BaseModel):
    items: list[ThreatBrief]
    total: int
    page:  int
    pages: int
    per_page: int


class ModuleInfo(BaseModel):
    """One entitlement row, projection for the /v1/licence endpoint."""
    module_sku: str
    edition:    str | None
    valid_to:   datetime | None
    feature_flags: dict[str, Any]
    limits:     dict[str, Any]
