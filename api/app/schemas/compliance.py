"""Pydantic payloads for compliance + reports + dashboard (Phase 5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- frameworks + controls ----------

class FrameworkBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    version: str
    authority: str | None
    jurisdiction: str | None
    description: str | None
    is_active: bool


class ControlBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    framework_id: UUID
    control_id: str
    title: str
    description: str | None
    # Verbatim regulatory clause — exactly as published in the source
    # document. The API never paraphrases this, never sends it to any LLM,
    # and serves the same byte-content for the same control_id on every run.
    requirement_text: str | None = None
    # Authoritative citation, e.g. "ISO/IEC 42001:2023 Annex A.4.3".
    source_ref: str | None = None
    category: str | None
    is_mandatory: bool
    applies_to: list[str] = Field(default_factory=list)
    evidence_hints: list[str] = Field(default_factory=list)


# ---------- mappings ----------

class MappingUpdate(BaseModel):
    status: str | None = None
    implementation_notes: str | None = None
    evidence_refs: list[str] | None = None
    next_review_date: str | None = None


class MappingDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    control_id: UUID
    ai_system_id: UUID | None
    status: str
    implementation_notes: str | None
    evidence_refs: list[str]
    last_assessed_at: datetime | None
    next_review_date: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------- framework score / gap report ----------

class FrameworkScoreResp(BaseModel):
    framework_id: UUID
    slug: str
    name: str
    total_controls: int
    by_status: dict[str, int]
    score_pct: float
    gaps: list[dict[str, Any]]


class AutoAssessResult(BaseModel):
    ok: bool
    framework: str | None = None
    controls: int = 0
    systems: int = 0
    assessed: int = 0
    error: str | None = None


# ---------- reports ----------

class ReportGenerateRequest(BaseModel):
    report_type: str = Field(..., description="executive_summary | framework_audit | risk_posture")
    framework_id: UUID | None = None
    file_format: str = "pdf"
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReportBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_type: str
    framework_id: UUID | None
    status: str
    file_format: str
    file_size_bytes: int | None
    error: str | None
    requested_at: datetime
    completed_at: datetime | None


# ---------- ecosystem map (for the D3 graph) ----------

class EcosystemNode(BaseModel):
    id: str
    name: str
    category: str
    risk_level: str | None
    is_shadow: bool
    usage_count: int
    department: str | None = None


class EcosystemEdge(BaseModel):
    source: str
    target: str
    kind: str = "data_flow"


class EcosystemGraph(BaseModel):
    nodes: list[EcosystemNode]
    edges: list[EcosystemEdge]


# ---------- dashboard overview ----------

class DashboardOverview(BaseModel):
    risk_posture_score: float
    total_systems: int
    shadow_count: int
    critical_count: int
    high_count: int
    aisia_pending_count: int
    violations_open: int
    framework_scores: list[FrameworkScoreResp]
    top_risks: list[dict[str, Any]]
    recent_discoveries: list[dict[str, Any]]
