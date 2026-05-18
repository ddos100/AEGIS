"""Endpoint Agent telemetry event (Phase 7.6) — TimescaleDB hypertable."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EndpointAgentEvent(Base):
    __tablename__ = "endpoint_agent_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", "occurred_at", name="pk_endpoint_agent_events"),
        CheckConstraint(
            "kind IN ('process_exec','file_write_to_watched_path',"
            "'secret_read_by_ai_proc','curl_pipe_sh_detected',"
            "'mcp_config_observed','package_install_pre_hook',"
            "'path_shadow_detected','autostart_artifact','heartbeat')",
            name="ck_endpoint_agent_events_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("endpoint_devices.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
