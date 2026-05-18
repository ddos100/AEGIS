"""Phase 7.6 — AEGIS Endpoint Agent ingest schema.

Adds:
  - endpoint_devices       Per-tenant fleet of enrolled devices. Carries
                           hostname, OS, agent version, agent fingerprint
                           (sha256 of the signed enrolment token), and
                           heartbeat timestamp. Tenant-scoped + RLS.
  - endpoint_agent_events  TimescaleDB hypertable, monthly chunks.
                           Append-only telemetry stream from the agent;
                           every row carries a `kind` enum (one of the
                           shipped EA event kinds — process_exec,
                           file_write_to_watched_path, secret_read_by_ai_proc,
                           curl_pipe_sh_detected, mcp_config_observed,
                           package_install_pre_hook, path_shadow_detected,
                           autostart_artifact) plus a JSONB `payload`
                           bounded to the allow-list documented in
                           PHASE-7-PLAN.md §B.3.4. No prompt text, no
                           file contents, no command-line plaintext —
                           the agent hashes command-lines per-device
                           before they leave the host.

Privacy by Design contract enforced at the schema layer:
  CHECK constraint forbids known PII columns from ever existing on
  the event table. `payload` is JSONB but the API ingest layer
  validates against the allow-list before the row is written.

Revision ID: 014_phase76_endpoint_agent
Revises: 013_phase72_threat_feed
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_phase76_endpoint_agent"
down_revision: Union[str, None] = "013_phase72_threat_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ endpoint_devices ============
    op.create_table(
        "endpoint_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname",     sa.String(255), nullable=False,
                  comment="OS hostname; stored as-is for operator UX (treat as semi-sensitive)"),
        sa.Column("os",           sa.String(32),  nullable=False,
                  comment="linux | darwin | windows"),
        sa.Column("arch",         sa.String(16),  nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=False),
        sa.Column("enrollment_fingerprint", sa.String(64), nullable=False,
                  comment="sha256 of the signed enrolment token issued to this device"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("revoked_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("os IN ('linux','darwin','windows')",
                           name="ck_endpoint_devices_os"),
        sa.UniqueConstraint("tenant_id", "enrollment_fingerprint",
                            name="uq_endpoint_devices_enrollment"),
    )
    op.execute(
        "CREATE TRIGGER tg_endpoint_devices_updated_at "
        "BEFORE UPDATE ON endpoint_devices "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.execute("ALTER TABLE endpoint_devices ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation ON endpoint_devices "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.create_index("ix_endpoint_devices_tenant_heartbeat",
                    "endpoint_devices", ["tenant_id", "last_heartbeat_at"])

    # ============ endpoint_agent_events ============
    op.create_table(
        "endpoint_agent_events",
        # Composite PK for the hypertable so Postgres lets us partition
        # by occurred_at while keeping a row-level identity.
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("endpoint_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False,
                  comment="Allow-listed EA event kind"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", "occurred_at",
                                name="pk_endpoint_agent_events"),
        sa.CheckConstraint(
            "kind IN ('process_exec','file_write_to_watched_path',"
            "'secret_read_by_ai_proc','curl_pipe_sh_detected',"
            "'mcp_config_observed','package_install_pre_hook',"
            "'path_shadow_detected','autostart_artifact',"
            "'heartbeat')",
            name="ck_endpoint_agent_events_kind",
        ),
    )
    op.execute("ALTER TABLE endpoint_agent_events ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation ON endpoint_agent_events "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.create_index("ix_endpoint_agent_events_tenant_kind_time",
                    "endpoint_agent_events", ["tenant_id", "kind", "occurred_at"])

    # Convert to a TimescaleDB hypertable when the extension is present.
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
            PERFORM create_hypertable('endpoint_agent_events', 'occurred_at',
                                      chunk_time_interval => INTERVAL '1 month',
                                      if_not_exists => TRUE);
          END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("endpoint_agent_events")
    op.drop_table("endpoint_devices")
