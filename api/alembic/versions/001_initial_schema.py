"""Initial schema — tenants, users, departments, ai_providers, audit_log + RLS policies.

Revision ID: 001_initial
Revises:
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")           # gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")        # hypertables (Phase 2)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")            # FTS (Phase 1)

    # --- updated_at trigger function (reused across tables) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # ============ tenants ============
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default="discovery"),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_tenants_slug", "tenants", ["slug"])
    op.execute("CREATE TRIGGER tg_tenants_updated_at BEFORE UPDATE ON tenants "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")

    # ============ users ============
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keycloak_sub", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("idx_users_tenant", "users", ["tenant_id"])
    op.create_index("idx_users_keycloak_sub", "users", ["keycloak_sub"])
    op.execute("CREATE TRIGGER tg_users_updated_at BEFORE UPDATE ON users "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_users ON users "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ departments ============
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_departments_tenant", "departments", ["tenant_id"])
    op.execute("CREATE TRIGGER tg_departments_updated_at BEFORE UPDATE ON departments "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE departments ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_departments ON departments "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ ai_providers (global, NOT tenant-scoped) ============
    op.create_table(
        "ai_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hq_country", sa.String(2), nullable=True),
        sa.Column("provider_type", sa.String(32), nullable=False, server_default="commercial_api"),
        sa.Column("trust_score", sa.SmallInteger(), nullable=True),
        sa.Column("data_residency", postgresql.ARRAY(sa.String(2)), nullable=True),
        sa.Column("privacy_url", sa.Text(), nullable=True),
        sa.Column("terms_url", sa.Text(), nullable=True),
        sa.Column("soc2_certified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("iso27001_cert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gdpr_dpa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("catalogue_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("trust_score BETWEEN 0 AND 100", name="ck_ai_providers_trust_score_range"),
    )
    op.execute("CREATE TRIGGER tg_ai_providers_updated_at BEFORE UPDATE ON ai_providers "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")

    # ============ audit_log (append-only) ============
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_log_tenant_time", "audit_log", ["tenant_id", "occurred_at"])
    op.create_index("idx_audit_log_action", "audit_log", ["action"])

    # Block UPDATE/DELETE on audit_log (append-only invariant).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("CREATE TRIGGER tg_audit_log_no_update BEFORE UPDATE ON audit_log "
               "FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();")
    op.execute("CREATE TRIGGER tg_audit_log_no_delete BEFORE DELETE ON audit_log "
               "FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tg_audit_log_no_update ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS tg_audit_log_no_delete ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_modify();")
    op.drop_table("audit_log")
    op.drop_table("ai_providers")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_departments ON departments;")
    op.drop_table("departments")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_users ON users;")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
