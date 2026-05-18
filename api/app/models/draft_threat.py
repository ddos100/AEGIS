"""Pending-review draft threat (Phase 7.2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class DraftThreat(Base):
    __tablename__ = "draft_threats"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending_review','published','rejected','superseded')",
            name="ck_draft_threats_status",
        ),
        UniqueConstraint("source_fingerprint", name="uq_draft_threats_fingerprint"),
    )

    id: Mapped[UUIDPk]
    source:             Mapped[str] = mapped_column(String(48), nullable=False)
    upstream_id:        Mapped[str] = mapped_column(String(255), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    draft:              Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    review_status:      Mapped[str] = mapped_column(String(24), nullable=False, default="pending_review")
    review_notes:       Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by:        Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reviewed_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_threat_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("threats.id", ondelete="SET NULL"), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
