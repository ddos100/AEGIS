"""Per-tenant module entitlement (Phase 7.1).

One row per active module SKU. The `@requires_module` dependency reads
the active rows for the current tenant on every gated request and
returns 402 if the module is missing or expired.

Dev tenant (00000000-…-001) is seeded with every module enabled by
Alembic 009 so `make up` runs end-to-end without a licence file.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class ModuleEntitlement(Base):
    __tablename__ = "modules_entitled"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_sku", name="uq_entitlements_tenant_module"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    module_sku: Mapped[str] = mapped_column(String(64), nullable=False)
    edition:    Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    valid_to:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    limits:        Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    licence_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
