"""Browser extension device enrollment record."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantFK, UUIDPk


class ExtensionDevice(Base):
    __tablename__ = "extension_devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "device_fingerprint", name="uq_extension_devices_fp"),
    )

    id: Mapped[UUIDPk]
    tenant_id: Mapped[uuid.UUID] = TenantFK()
    device_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extension_version: Mapped[str] = mapped_column(String(32), nullable=False)
    os_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
