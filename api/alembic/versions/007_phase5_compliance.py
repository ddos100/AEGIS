"""Phase 5 — Compliance + Reporting.

Adds:
  - compliance_frameworks  Global catalogue of regulatory frameworks.
  - compliance_controls    Individual controls within each framework.
  - compliance_mappings    Per-tenant assessment of each control (tenant- or
                           per-system scope). Status: implemented | partial |
                           not_implemented | not_applicable | not_assessed.
  - reports                Generated audit/executive report history.

Frameworks + controls are global (admin-maintained, no tenant_id). Mappings
and reports are tenant-scoped with RLS.

Revision ID: 007_phase5_compliance
Revises: 006_phase4_risk_policy
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_phase5_compliance"
down_revision: Union[str, None] = "006_phase4_risk_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ compliance_frameworks (global) ============
    op.create_table(
        "compliance_frameworks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("authority",  sa.String(128), nullable=True),  # e.g. ISO, EU, NIST, RBI
        sa.Column("jurisdiction", sa.String(32), nullable=True), # e.g. IN, EU, US, global
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE TRIGGER tg_frameworks_updated_at BEFORE UPDATE ON compliance_frameworks "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")

    # ============ compliance_controls (global, per-framework) ============
    op.create_table(
        "compliance_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("control_id", sa.String(64), nullable=False),    # e.g. "ISO42001-A.4.3"
        sa.Column("title",      sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category",    sa.String(64), nullable=True),    # governance | risk | data | operations | lifecycle | supply_chain
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("applies_to",  postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),         # ai_provider | ai_user | both
        sa.Column("evidence_hints", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        # Optional AISystem fields that, when present, satisfy this control.
        # The engine uses these to auto-mark controls as 'partial' (never
        # 'implemented' — that requires human attestation).
        sa.Column("auto_check", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("framework_id", "control_id", name="uq_controls_control_id"),
    )
    op.create_index("idx_controls_framework", "compliance_controls", ["framework_id"])

    # ============ compliance_mappings (per-tenant) ============
    op.create_table(
        "compliance_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("compliance_controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_assessed"),
        sa.Column("implementation_notes", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "control_id", "ai_system_id", name="uq_mappings_unique"),
    )
    op.create_index("idx_mappings_tenant_status", "compliance_mappings",
                    ["tenant_id", "status"])
    op.create_index("idx_mappings_tenant_control", "compliance_mappings",
                    ["tenant_id", "control_id"])
    op.execute("CREATE TRIGGER tg_mappings_updated_at BEFORE UPDATE ON compliance_mappings "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE compliance_mappings ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_mappings ON compliance_mappings "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ reports ============
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("file_format", sa.String(8), nullable=False, server_default="pdf"),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_reports_tenant_time", "reports",
                    ["tenant_id", sa.text("requested_at DESC")])
    op.execute("ALTER TABLE reports ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_reports ON reports "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )


def downgrade() -> None:
    for tbl in ("reports", "compliance_mappings"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl.replace('compliance_','')} ON {tbl};")
    op.drop_table("reports")
    op.drop_table("compliance_mappings")
    op.drop_table("compliance_controls")
    op.drop_table("compliance_frameworks")
