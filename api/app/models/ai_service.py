"""Global AI Service Catalogue entry — read-only for tenants, maintained by SCLLP."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ARRAY, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, UUIDPk


class AIService(Base, CreatedUpdatedMixin):
    __tablename__ = "ai_services"

    id: Mapped[UUIDPk]
    catalogue_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_providers.id"), nullable=True
    )
    provider_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Discovery patterns — matched by the Aho-Corasick automaton in Phase 2.
    api_patterns: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    browser_domains: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    entra_app_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)

    # Classification
    eu_ai_act_cat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    input_types: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    output_types: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    hq_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    gdpr_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    risk_hints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    catalogue_version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
