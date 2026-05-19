"""Pydantic schemas for the AEGIS Endpoint Agent (Phase 7.6)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ALLOWED_KINDS = Literal[
    "process_exec",
    "file_write_to_watched_path",
    "secret_read_by_ai_proc",
    "curl_pipe_sh_detected",
    "mcp_config_observed",
    "package_install_pre_hook",
    "path_shadow_detected",
    "autostart_artifact",
    "heartbeat",
    # Phase 7.6 v0.2.0 — procmon + netmon
    "ai_process_running",
    "ai_provider_connection",
    "destructive_cmd_correlation",
]


# ---------- enrolment ----------

class EnrollmentRequest(BaseModel):
    """Admin generates a one-time enrolment code in the UI; the agent
    exchanges that for a long-lived device token via this endpoint."""
    enrollment_code: str = Field(..., min_length=8, max_length=128)
    hostname:       str  = Field(..., min_length=1, max_length=255)
    os:             Literal["linux", "darwin", "windows"]
    arch:           str  = Field(..., min_length=1, max_length=16)
    agent_version:  str  = Field(..., min_length=1, max_length=32)


class EnrollmentResponse(BaseModel):
    device_id:        UUID
    agent_token:      str = Field(..., description="Signed device-scoped token; carry as Bearer.")
    ingest_url:       str
    heartbeat_seconds: int = 60


class DeviceBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  UUID
    hostname:            str
    os:                  str
    arch:                str
    agent_version:       str
    last_heartbeat_at:   datetime | None
    enrolled_at:         datetime
    revoked_at:          datetime | None


class DeviceListResponse(BaseModel):
    items: list[DeviceBrief]
    total: int
    healthy: int = Field(description="Devices that heartbeated in the last 5 minutes")


class EnrollmentCodeResponse(BaseModel):
    """Admin generates an enrolment code to bootstrap a new device."""
    enrollment_code: str
    expires_at:      datetime
    ingest_url:      str


# ---------- event ingest ----------

class EAEvent(BaseModel):
    """One event in an agent batch.

    Schema enforces the allow-list of `kind` + bounds the payload to a
    bounded dict. The route layer additionally rejects any payload key
    that smells like PII (`prompt`, `email`, `body`, `content`, `path`
    without the `_pattern` suffix, etc.) before persisting.
    """
    kind:        ALLOWED_KINDS
    occurred_at: datetime
    payload:     dict[str, Any] = Field(default_factory=dict)


class EABatch(BaseModel):
    device_id:   UUID
    events:      list[EAEvent] = Field(..., min_length=0, max_length=1000)


class IngestReceipt(BaseModel):
    accepted: int
    rejected: int = 0
    rejected_reasons: list[str] = Field(default_factory=list)
    heartbeat_seconds: int = 60


# ---------- query (admin/analyst view) ----------

class EAEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          UUID
    device_id:   UUID
    kind:        str
    occurred_at: datetime
    ingested_at: datetime
    payload:     dict[str, Any] = Field(default_factory=dict)
    hostname:    str | None = None


class EAEventListResponse(BaseModel):
    items: list[EAEventOut]
    by_kind: dict[str, int]
    total: int
