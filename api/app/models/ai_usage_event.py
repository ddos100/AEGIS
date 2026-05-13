"""TimescaleDB-backed observation record from any discovery vector."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    # Composite primary key (id, occurred_at) matches the TimescaleDB hypertable.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)

    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True
    )
    catalogue_service_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_services.id", ondelete="SET NULL"), nullable=True
    )
    catalogue_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_url_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bytes_sent: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bytes_recv: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
