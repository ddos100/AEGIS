"""AI System Impact Assessment record (ISO 42001 Clause 6.1.2)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, TenantFK, UUIDPk


class AISIARecord(Base, CreatedUpdatedMixin):
    __tablename__ = "aisia_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ai_system_id", name="uq_aisia_per_system"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    status:       Mapped[str] = mapped_column(String(32), nullable=False, default="initiated")
    impact_level: Mapped[str | None] = mapped_column(String(16), nullable=True)

    intended_purpose_confirmed: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_population:        Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_assessment:        Mapped[str | None] = mapped_column(Text, nullable=True)
    reversibility_assessment:   Mapped[str | None] = mapped_column(Text, nullable=True)
    human_oversight_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_decision:         Mapped[str | None] = mapped_column(String(32), nullable=True)
    societal_impact_notes:      Mapped[str | None] = mapped_column(Text, nullable=True)

    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_to:  Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by:  Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date:         Mapped[date | None] = mapped_column(Date, nullable=True)
    ai_draft:         Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes:     Mapped[str | None] = mapped_column(Text, nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
