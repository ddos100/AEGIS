from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, TenantFK, UUIDPk


class Policy(Base, CreatedUpdatedMixin):
    """Tenant-scoped policy rule. Conditions are AND-combined; the first
    matching policy by priority wins. Action is one of:
    allow | monitor | alert | block | require_approval."""
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "priority", name="uq_policies_priority"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    action_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
