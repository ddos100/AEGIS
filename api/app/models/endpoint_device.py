"""Endpoint Agent device record (Phase 7.6)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class EndpointDevice(Base):
    __tablename__ = "endpoint_devices"
    __table_args__ = (
        CheckConstraint("os IN ('linux','darwin','windows')",
                        name="ck_endpoint_devices_os"),
        UniqueConstraint("tenant_id", "enrollment_fingerprint",
                         name="uq_endpoint_devices_enrollment"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    hostname:     Mapped[str] = mapped_column(String(255), nullable=False)
    os:           Mapped[str] = mapped_column(String(32), nullable=False)
    arch:         Mapped[str] = mapped_column(String(16), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    enrollment_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
