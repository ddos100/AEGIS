"""Per-tenant threat exposure verdict (Phase 7.1).

One row per (tenant_id, threat_id). Written by the exposure-evaluation
engine; never overwritten silently — status changes carry a fresh
reasons[] + evidence_refs[] composed by the engine on that run.

Verdicts are exhaustive: every threat in a tenant's view ends as
`exposed`, `not_exposed`, `unknown`, or (post Phase 7.5) `mitigated`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class ThreatExposure(Base):
    __tablename__ = "threat_exposures"
    __table_args__ = (
        CheckConstraint(
            "status IN ('exposed','not_exposed','unknown','mitigated')",
            name="ck_threat_exposures_status",
        ),
        UniqueConstraint("tenant_id", "threat_id", name="uq_threat_exposures_unique"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    threat_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("threats.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(ARRAY(String(300)), nullable=False, default=list)
    missing_telemetry: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
