from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, TenantFK, UUIDPk


class ComplianceMapping(Base, CreatedUpdatedMixin):
    __tablename__ = "compliance_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "control_id", "ai_system_id",
                         name="uq_mappings_unique"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    control_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("compliance_controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_assessed")
    implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    last_assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
