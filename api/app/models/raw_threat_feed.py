"""Append-only raw upstream feed log (Phase 7.2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class RawThreatFeed(Base):
    __tablename__ = "raw_threat_feed"
    __table_args__ = (
        UniqueConstraint("source", "payload_sha256", name="uq_raw_threat_feed_dedup"),
    )

    id: Mapped[UUIDPk]
    source:      Mapped[str] = mapped_column(String(48), nullable=False)
    upstream_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload:     Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
