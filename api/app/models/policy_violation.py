from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantFK, UUIDPk


class PolicyViolation(Base):
    """Append-only record of a non-allow policy decision."""
    __tablename__ = "policy_violations"

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    policy_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    vector: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(32), nullable=False)
    violation_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
