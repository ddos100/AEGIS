"""Pydantic schemas for the Exposure-evaluation API (Phase 7.1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExposureBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:        UUID
    tenant_id: UUID
    threat_id: UUID
    status:    str
    last_evaluated_at: datetime
    # threat metadata projected by the API for the list page
    threat_external_id: str
    threat_title:       str
    threat_severity:    str
    threat_classes:     list[str] = Field(default_factory=list)
    threat_vectors:     list[str] = Field(default_factory=list)


class ExposureDetail(ExposureBrief):
    reasons:           list[str] = Field(default_factory=list)
    evidence_refs:     list[str] = Field(default_factory=list)
    missing_telemetry: list[str] = Field(default_factory=list)
    threat_source_ref: str
    threat_verbatim_description: str
    threat_exposure_check: dict[str, Any] = Field(default_factory=dict)
    threat_mitigation: dict[str, Any] | None = None


class ExposureListResponse(BaseModel):
    items: list[ExposureBrief]
    by_status: dict[str, int]
    total: int


class RecomputeResponse(BaseModel):
    tenant_id:         str
    threats_total:     int
    exposed:           int
    not_exposed:       int
    unknown:           int
    skipped_by_sector: int
