"""Pydantic schemas for risk, AISIA, policy, violations (Phase 4)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- Risk ----------

class RiskAssessmentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ai_system_id: UUID
    data_sensitivity_score: int
    ai_capability_score: int
    regulatory_exposure_score: int
    access_scope_score: int
    provider_trust_score: int
    total_score: int
    risk_level: str
    scoring_inputs: dict[str, Any] = Field(default_factory=dict)
    ai_narrative: str | None
    ai_model_used: str | None
    calculated_by: str
    calculated_at: datetime


class RiskSummary(BaseModel):
    total_systems: int
    by_level: dict[str, int]
    avg_score: float
    top_drivers: list[dict[str, Any]]


# ---------- AISIA ----------

AISIA_STATUSES = ("initiated", "in_progress", "completed", "approved", "rejected")
TREATMENT_DECISIONS = ("accept", "restrict", "block")


class AISIAUpdate(BaseModel):
    """Partial-update body — operators progress the assessment one step at a time."""
    intended_purpose_confirmed: str | None = None
    affected_population:        str | None = None
    severity_assessment:        str | None = None
    reversibility_assessment:   str | None = None
    human_oversight_assessment: str | None = None
    treatment_decision:         str | None = None
    societal_impact_notes:      str | None = None
    impact_level:               str | None = None
    review_notes:               str | None = None
    next_review_date:           date | None = None
    status:                     str | None = None


class AISIADetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ai_system_id: UUID
    status: str
    impact_level: str | None
    intended_purpose_confirmed: str | None
    affected_population: str | None
    severity_assessment: str | None
    reversibility_assessment: str | None
    human_oversight_assessment: str | None
    treatment_decision: str | None
    societal_impact_notes: str | None
    initiated_by: UUID | None
    initiated_at: datetime
    assigned_to: UUID | None
    completed_by: UUID | None
    completed_at: datetime | None
    approved_by: UUID | None
    approved_at: datetime | None
    due_date: date | None
    ai_draft: str | None
    review_notes: str | None
    next_review_date: date | None
    created_at: datetime
    updated_at: datetime


# ---------- Policy ----------

class PolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: int = Field(..., ge=1, le=10000)
    conditions: dict[str, Any] = Field(default_factory=dict)
    action: str = Field(..., description="allow|monitor|alert|block|require_approval")
    action_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    template_id: str | None = None


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    priority: int | None = Field(default=None, ge=1, le=10000)
    conditions: dict[str, Any] | None = None
    action: str | None = None
    action_config: dict[str, Any] | None = None
    is_active: bool | None = None


class PolicyDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    is_active: bool
    priority: int
    conditions: dict[str, Any] = Field(default_factory=dict)
    action: str
    action_config: dict[str, Any] = Field(default_factory=dict)
    template_id: str | None
    created_at: datetime
    updated_at: datetime


class PolicyTestRequest(BaseModel):
    ai_system_id: UUID
    user_groups: list[str] = Field(default_factory=list)


class PolicyTestResponse(BaseModel):
    action: str
    policy_id: UUID | None
    policy_name: str | None
    matched_conditions: list[str]
    config: dict[str, Any] = Field(default_factory=dict)


class PolicyReorderRequest(BaseModel):
    ordered_ids: list[UUID]


class PolicyTemplateBrief(BaseModel):
    id: str
    name: str
    description: str
    rule_count: int


# ---------- Violations ----------

class ViolationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    ai_system_id: UUID | None
    user_id: UUID | None
    vector: str | None
    action_taken: str
    violation_context: dict[str, Any] = Field(default_factory=dict)
    resolved: bool
    resolved_by: UUID | None
    resolved_at: datetime | None
    resolution_notes: str | None
    occurred_at: datetime


class ViolationResolve(BaseModel):
    notes: str | None = None
