"""Point-in-time risk assessment row (TimescaleDB hypertable)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    # (id, calculated_at) matches the hypertable partitioning.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False
    )

    data_sensitivity_score:    Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ai_capability_score:       Mapped[int] = mapped_column(SmallInteger, nullable=False)
    regulatory_exposure_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    access_scope_score:        Mapped[int] = mapped_column(SmallInteger, nullable=False)
    provider_trust_score:      Mapped[int] = mapped_column(SmallInteger, nullable=False)
    total_score: Mapped[int]  = mapped_column(SmallInteger, nullable=False)
    risk_level:  Mapped[str]  = mapped_column(String(16),   nullable=False)

    scoring_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ai_narrative:   Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_model_used:  Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculated_by:  Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
