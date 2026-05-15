from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedUpdatedMixin, UUIDPk


class ComplianceFramework(Base, CreatedUpdatedMixin):
    __tablename__ = "compliance_frameworks"

    id: Mapped[UUIDPk]
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    authority: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(32), nullable=True)
