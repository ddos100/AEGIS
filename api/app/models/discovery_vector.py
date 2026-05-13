"""Per-tenant configuration record for a single discovery vector source."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, TenantFK, UUIDPk


class DiscoveryVector(Base, CreatedUpdatedMixin):
    __tablename__ = "discovery_vectors"

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    vector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    events_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
