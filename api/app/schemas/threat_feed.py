"""Pydantic schemas for the Threat-Feed review queue (Phase 7.2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DraftBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  UUID
    source:              str
    upstream_id:         str
    review_status:       str
    ingested_at:         datetime
    reviewed_at:         datetime | None
    threat_id:           str = Field(description="Draft.threat_id — proposed catalogue ID")
    title:               str
    severity:            str
    classes:             list[str]
    vectors:             list[str]


class DraftDetail(DraftBrief):
    draft:           dict[str, Any]
    review_notes:    str | None = None
    source_fingerprint: str
    published_threat_id: UUID | None = None


class DraftListResponse(BaseModel):
    items:     list[DraftBrief]
    by_status: dict[str, int]
    total:     int


class DraftDecisionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class PublishRequest(DraftDecisionRequest):
    """Publish a draft — optionally with operator edits.

    `edited_draft` lets the reviewer override fields before the row
    becomes canonical. When None, the original draft is used verbatim.
    The result is upserted into `threats` AND written out as
    catalogue/threats/<source>/<threat_id>.yaml so the file remains
    the source of truth.
    """
    edited_draft: dict[str, Any] | None = None
    write_yaml: bool = Field(
        default=True,
        description="When True (default), publish writes the YAML file under "
                    "catalogue/threats/<source>/<threat_id>.yaml. Set to False "
                    "for ephemeral / dev-only publishes that should not touch git.",
    )


class FeedSourceInfo(BaseModel):
    source: str
    cls:    str = Field(alias="class")
    default_jurisdictions: list[str]

    model_config = ConfigDict(populate_by_name=True)


class IngestRunResult(BaseModel):
    source:     str
    ok:         bool
    seen:       int = 0
    drafted:    int = 0
    duplicates: int = 0
    skipped:    int = 0
    errored:    int = 0
    error:      str | None = None
