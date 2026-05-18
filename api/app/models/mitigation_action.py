"""Mitigation-action record (Phase 7.4).

One row per (tenant, threat, mitigation step). Append-only history:
once a row reaches a terminal state (rejected, applied, verified,
rolled_back, failed) it is NEVER overwritten. New cycles produce new
rows distinguished by idempotency_key.

The orchestrator (services/mitigation_orchestrator.py) writes status
transitions; the API exposes them to the operator who approves, rejects,
or dismisses. Actual vendor pushes are deferred to Phase 7.5.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class MitigationAction(Base):
    __tablename__ = "mitigation_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed','rejected','dismissed','queued','applied',"
            "'verified','drifted','rolled_back','failed')",
            name="ck_mitigation_actions_status",
        ),
        CheckConstraint(
            "preference IN ('preferred','alternate')",
            name="ck_mitigation_actions_preference",
        ),
        UniqueConstraint("tenant_id", "idempotency_key",
                         name="uq_mitigation_actions_idempotency"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    threat_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("threats.id", ondelete="CASCADE"), nullable=False
    )
    exposure_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("threat_exposures.id", ondelete="SET NULL"), nullable=True
    )
    integration:   Mapped[str] = mapped_column(String(64),  nullable=False)
    action:        Mapped[str] = mapped_column(String(120), nullable=False)
    params:        Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    severity_min:  Mapped[str | None] = mapped_column(String(16), nullable=True)
    requires_module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preference:    Mapped[str] = mapped_column(String(16), nullable=False, default="preferred")
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status:        Mapped[str] = mapped_column(String(20),  nullable=False, default="proposed")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    approved_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by:  Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    applied_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error:   Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
