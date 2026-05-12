from __future__ import annotations

from typing import Any

from sqlalchemy import ARRAY, Boolean, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, UUIDPk


class AIProvider(Base, CreatedUpdatedMixin):
    """Global AI vendor catalogue — read-only for tenants, maintained by SCLLP."""

    __tablename__ = "ai_providers"

    id: Mapped[UUIDPk]
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hq_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, default="commercial_api")
    trust_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    data_residency: Mapped[list[str] | None] = mapped_column(ARRAY(String(2)), nullable=True)
    privacy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    soc2_certified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    iso27001_cert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gdpr_dpa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    catalogue_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
