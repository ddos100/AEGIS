from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class ComplianceControl(Base):
    __tablename__ = "compliance_controls"
    __table_args__ = (
        UniqueConstraint("framework_id", "control_id", name="uq_controls_control_id"),
    )

    id: Mapped[UUIDPk]
    framework_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=False
    )
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    applies_to: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    evidence_hints: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    auto_check: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
