"""AI System Registry entry — tenant-scoped (RLS).

Implements the ISO 42001 Clause 4 AI System Register operationalised as a
relational record. Auto-populated by the Discovery Engine and enrichable
by humans. The ``completeness_score`` and ``risk_level`` columns are
maintained by DB-side triggers/computed columns.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, Date, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, TenantFK, UUIDPk


class AISystem(Base, CreatedUpdatedMixin):
    __tablename__ = "ai_systems"

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()

    # --- Identity ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalogue_service_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_services.id"), nullable=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_providers.id"), nullable=True
    )
    provider_name_freetext: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Classification ---
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deployment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="cloud_saas")
    deployment_env: Mapped[str] = mapped_column(String(32), nullable=False, default="production")

    # --- ISO 42001 Clause 4 mandatory fields ---
    intended_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_use_observed: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_population: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_data_subjects: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )
    data_types_processed: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )
    output_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_oversight_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    geographic_scope: Mapped[list[str]] = mapped_column(ARRAY(String(2)), nullable=False, default=list)

    # --- Ownership ---
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    business_unit: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- Lifecycle ---
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    first_deployed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    decommission_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Discovery metadata ---
    discovery_sources: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    first_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Risk ---
    current_risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # risk_level is a stored generated column (set by Postgres from current_risk_score).
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_risk_assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Compliance ---
    aisia_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    aisia_impact_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    eu_ai_act_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_status: Mapped[str] = mapped_column(String(32), nullable=False, default="allow")
    compliance_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Completeness (DB-trigger maintained) ---
    completeness_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # --- Metadata ---
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
