"""Threat catalogue model (Phase 7.1).

Global, admin-maintained, read-only for tenants. Populated from
catalogue/threats/**/*.yaml via the threats_importer script. Every
record is required by schema validation to declare a non-empty
`exposure_check` predicate map.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import ARRAY, CheckConstraint, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk


class Threat(Base):
    __tablename__ = "threats"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical','high','medium','low')",
            name="ck_threats_severity",
        ),
    )

    id: Mapped[UUIDPk]
    threat_id:         Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title:             Mapped[str] = mapped_column(String(300), nullable=False)
    source_ref:        Mapped[str] = mapped_column(Text, nullable=False)
    verbatim_description: Mapped[str] = mapped_column(Text, nullable=False)
    description:       Mapped[str | None] = mapped_column(Text, nullable=True)
    severity:          Mapped[str] = mapped_column(String(16), nullable=False)
    classes:           Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    vectors:           Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    mitre_atlas_ids:   Mapped[list[str] | None] = mapped_column(ARRAY(String(32)), nullable=True)
    owasp_llm_ids:     Mapped[list[str] | None] = mapped_column(ARRAY(String(32)), nullable=True)
    sector_amplifiers: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)), nullable=True)
    applies_to_jurisdictions: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)), nullable=True)
    exposure_check:    Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    mitigation:        Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence_hints:    Mapped[list[str] | None] = mapped_column(ARRAY(String(300)), nullable=True)
    compliance_implications: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), nullable=True)
    catalogue_version: Mapped[str]  = mapped_column(String(32), nullable=False)
    last_updated:      Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
