"""Phase 2 — Discovery pipeline tables.

Adds:
  - ai_usage_events  TimescaleDB hypertable storing every observation
                     from any discovery vector (network/proxy/NGFW/DNS/XDR/
                     browser-ext/SaaS-audit/cloud/code).
  - ai_usage_hourly  Continuous aggregate over ai_usage_events; the dashboard
                     reads this, never the raw hypertable.
  - discovery_vectors  Per-tenant configuration for each enabled vector.
  - extension_devices  Browser-extension device registry.

Revision ID: 003_discovery_pipeline
Revises: 002_catalogue_registry
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_discovery_pipeline"
down_revision: Union[str, None] = "002_catalogue_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ ai_usage_events ============
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True),
        sa.Column("catalogue_service_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("catalogue_slug", sa.String(120), nullable=True),
        sa.Column("raw_domain", sa.String(255), nullable=True),
        sa.Column("raw_url_path", sa.String(255), nullable=True),
        sa.Column("vector", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("user_email", sa.String(320), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("source_ip", postgresql.INET(), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("process_name", sa.String(255), nullable=True),
        sa.Column("process_hash", sa.String(128), nullable=True),
        sa.Column("bytes_sent", sa.BigInteger(), nullable=True),
        sa.Column("bytes_recv", sa.BigInteger(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("raw_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", "occurred_at"),
    )
    # TimescaleDB hypertable — partitioned by month, auto-compressed after 7 days.
    op.execute(
        "SELECT create_hypertable('ai_usage_events', 'occurred_at', "
        "chunk_time_interval => INTERVAL '1 month', if_not_exists => TRUE);"
    )
    op.execute(
        "ALTER TABLE ai_usage_events SET ("
        "  timescaledb.compress, "
        "  timescaledb.compress_segmentby = 'tenant_id, ai_system_id', "
        "  timescaledb.compress_orderby = 'occurred_at DESC');"
    )
    op.execute(
        "SELECT add_compression_policy('ai_usage_events', INTERVAL '7 days', "
        "if_not_exists => TRUE);"
    )
    # Hot indexes for the query patterns we care about:
    op.create_index("idx_usage_tenant_time",   "ai_usage_events",
                    ["tenant_id", sa.text("occurred_at DESC")])
    op.create_index("idx_usage_system_time",   "ai_usage_events",
                    ["ai_system_id", sa.text("occurred_at DESC")])
    op.create_index("idx_usage_vector",        "ai_usage_events", ["tenant_id", "vector"])
    op.create_index("idx_usage_catalogue",     "ai_usage_events", ["tenant_id", "catalogue_slug"])
    op.create_index("idx_usage_user_email",    "ai_usage_events", ["tenant_id", "user_email"])

    # Continuous aggregate — hourly counts per (tenant, system, vector).
    # The dashboard reads ONLY from this view, never from the raw hypertable.
    op.execute(
        """
        CREATE MATERIALIZED VIEW ai_usage_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            tenant_id,
            ai_system_id,
            catalogue_slug,
            vector,
            time_bucket('1 hour', occurred_at) AS bucket,
            COUNT(*)                            AS event_count,
            COUNT(DISTINCT user_email)          AS unique_users,
            COALESCE(SUM(bytes_sent), 0)        AS total_bytes_sent,
            COALESCE(SUM(bytes_recv), 0)        AS total_bytes_recv
        FROM ai_usage_events
        GROUP BY tenant_id, ai_system_id, catalogue_slug, vector, bucket
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('ai_usage_hourly',
            start_offset => INTERVAL '7 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '15 minutes',
            if_not_exists => TRUE);
        """
    )
    # Daily retention metadata — actual retention is operator-tunable per tenant.
    op.execute(
        "SELECT add_retention_policy('ai_usage_events', INTERVAL '90 days', if_not_exists => TRUE);"
    )

    # ============ discovery_vectors ============
    op.create_table(
        "discovery_vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vector_type", sa.String(32), nullable=False),       # network|browser_ext|endpoint|...
        sa.Column("source", sa.String(64), nullable=False),            # zscaler|crowdstrike|squid|...
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("events_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_discovery_vectors_tenant", "discovery_vectors", ["tenant_id"])
    op.execute("CREATE TRIGGER tg_discovery_vectors_updated_at BEFORE UPDATE ON discovery_vectors "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE discovery_vectors ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_discovery_vectors ON discovery_vectors "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ extension_devices ============
    op.create_table(
        "extension_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_fingerprint", sa.String(128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_email", sa.String(320), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("browser_version", sa.String(64), nullable=True),
        sa.Column("extension_version", sa.String(32), nullable=False),
        sa.Column("os_platform", sa.String(32), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "device_fingerprint", name="uq_extension_devices_fp"),
    )
    op.create_index("idx_extension_devices_tenant", "extension_devices", ["tenant_id"])
    op.execute("ALTER TABLE extension_devices ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_extension_devices ON extension_devices "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_extension_devices ON extension_devices;")
    op.drop_table("extension_devices")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_discovery_vectors ON discovery_vectors;")
    op.drop_table("discovery_vectors")
    op.execute("SELECT remove_retention_policy('ai_usage_events', if_exists => TRUE);")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ai_usage_hourly CASCADE;")
    op.drop_table("ai_usage_events")
