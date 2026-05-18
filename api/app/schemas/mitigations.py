"""Pydantic schemas for mitigation actions (Phase 7.4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MitigationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:             UUID
    tenant_id:      UUID
    threat_id:      UUID
    exposure_id:    UUID | None
    integration:    str
    action:         str
    preference:     str
    requires_module: str | None
    severity_min:   str | None
    status:         str
    status_reason:  str | None
    proposed_at:    datetime
    approved_at:    datetime | None
    applied_at:     datetime | None
    verified_at:    datetime | None
    rolled_back_at: datetime | None
    # Joined threat metadata for the list page
    threat_external_id: str
    threat_title:       str
    threat_severity:    str


class MitigationDetail(MitigationBrief):
    params:          dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    last_error:      str | None = None
    threat_source_ref: str


class MitigationListResponse(BaseModel):
    items:     list[MitigationBrief]
    by_status: dict[str, int]
    total:     int


class MitigationDecisionRequest(BaseModel):
    """Body for approve / reject / dismiss endpoints."""
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional free-text justification recorded on the row.",
    )
