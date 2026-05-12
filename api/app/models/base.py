"""Declarative base + shared mixins (UUID PK, timestamps, tenant_id)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base. Models inherit from this directly."""


UUIDPk = Annotated[
    uuid.UUID,
    mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
]

TimestampMixin = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False),
]


class CreatedUpdatedMixin:
    """Adds created_at / updated_at columns with DB-side defaults."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def TenantFK() -> "Mapped[uuid.UUID]":  # noqa: N802 — used as a factory
    """Standard tenant_id foreign key column for tenant-scoped tables."""
    return mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
