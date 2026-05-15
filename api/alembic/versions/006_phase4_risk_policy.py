"""Phase 4 — Risk Assessment Engine + Policy Engine.

Adds:
  - risk_assessments   TimescaleDB hypertable storing point-in-time risk
                       scores per AI system. The Registry shows the latest;
                       history is kept for audit + trend analysis.
  - aisia_records      One-to-one with an AISystem when status >= 'in_progress'.
                       Implements the ISO 42001 Clause 6.1.2 six-step workflow.
  - policies           Tenant-scoped rule definitions (conditions+actions).
                       Priority unique per tenant — first match wins.
  - policy_violations  Append-only log of every policy decision that wasn't
                       allow (alert/monitor/block/require_approval).

Revision ID: 006_phase4_risk_policy
Revises: 005_phase3_integrations
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_phase4_risk_policy"
down_revision: Union[str, None] = "005_phase3_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ risk_assessments (TimescaleDB hypertable) ============
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False),
        # 5 dimension scores (each 0-100)
        sa.Column("data_sensitivity_score",    sa.SmallInteger(), nullable=False),
        sa.Column("ai_capability_score",       sa.SmallInteger(), nullable=False),
        sa.Column("regulatory_exposure_score", sa.SmallInteger(), nullable=False),
        sa.Column("access_scope_score",        sa.SmallInteger(), nullable=False),
        sa.Column("provider_trust_score",      sa.SmallInteger(), nullable=False),
        # Composite (weighted 0-100)
        sa.Column("total_score", sa.SmallInteger(), nullable=False),
        sa.Column("risk_level",  sa.String(16), nullable=False),
        # Inputs snapshot for audit reproducibility
        sa.Column("scoring_inputs", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        # Claude-generated narrative (Critical/High only, NULL otherwise)
        sa.Column("ai_narrative",  sa.Text(), nullable=True),
        sa.Column("ai_model_used", sa.String(64), nullable=True),
        # Metadata
        sa.Column("calculated_by", sa.String(32), nullable=False, server_default="auto"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", "calculated_at"),
        sa.CheckConstraint("total_score BETWEEN 0 AND 100", name="ck_risk_total_range"),
    )
    op.execute(
        "SELECT create_hypertable('risk_assessments', 'calculated_at', "
        "chunk_time_interval => INTERVAL '3 months', if_not_exists => TRUE);"
    )
    op.create_index("idx_risk_tenant_time", "risk_assessments",
                    ["tenant_id", sa.text("calculated_at DESC")])
    op.create_index("idx_risk_system_time", "risk_assessments",
                    ["ai_system_id", sa.text("calculated_at DESC")])

    # ============ aisia_records ============
    op.create_table(
        "aisia_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status",       sa.String(32), nullable=False, server_default="initiated"),  # initiated|in_progress|completed|approved|rejected
        sa.Column("impact_level", sa.String(16), nullable=True),                                 # low|medium|high
        # ISO 42001 Clause 6.1.2 — six dimensions, all free text
        sa.Column("intended_purpose_confirmed", sa.Text(), nullable=True),
        sa.Column("affected_population",        sa.Text(), nullable=True),
        sa.Column("severity_assessment",        sa.Text(), nullable=True),
        sa.Column("reversibility_assessment",   sa.Text(), nullable=True),
        sa.Column("human_oversight_assessment", sa.Text(), nullable=True),
        sa.Column("treatment_decision",         sa.String(32), nullable=True),  # accept|restrict|block
        sa.Column("societal_impact_notes",      sa.Text(), nullable=True),
        # Workflow
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("assigned_to",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date",         sa.Date(), nullable=True),
        sa.Column("ai_draft",         sa.Text(), nullable=True),
        sa.Column("review_notes",     sa.Text(), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "ai_system_id", name="uq_aisia_per_system"),
    )
    op.create_index("idx_aisia_tenant_status", "aisia_records", ["tenant_id", "status"])
    op.execute("CREATE TRIGGER tg_aisia_updated_at BEFORE UPDATE ON aisia_records "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE aisia_records ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_aisia ON aisia_records "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ policies ============
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active",   sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority",    sa.Integer(), nullable=False),
        sa.Column("conditions",  postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("action",        sa.String(32), nullable=False),    # allow|monitor|alert|block|require_approval
        sa.Column("action_config", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("template_id", sa.String(64), nullable=True),
        sa.Column("created_by",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "priority", name="uq_policies_priority"),
    )
    op.create_index("idx_policies_active", "policies",
                    ["tenant_id", "priority"],
                    postgresql_where=sa.text("is_active = true"))
    op.execute("CREATE TRIGGER tg_policies_updated_at BEFORE UPDATE ON policies "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE policies ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_policies ON policies "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ policy_violations ============
    op.create_table(
        "policy_violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vector",      sa.String(32), nullable=True),
        sa.Column("action_taken", sa.String(32), nullable=False),
        sa.Column("violation_context", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved",    sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("occurred_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_violations_tenant", "policy_violations",
                    ["tenant_id", sa.text("occurred_at DESC")])
    op.create_index("idx_violations_policy", "policy_violations", ["tenant_id", "policy_id"])
    op.create_index("idx_violations_unresolved", "policy_violations",
                    ["tenant_id", sa.text("occurred_at DESC")],
                    postgresql_where=sa.text("resolved = false"))
    op.execute("ALTER TABLE policy_violations ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_violations ON policy_violations "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )


def downgrade() -> None:
    for tbl in ("policy_violations", "policies", "aisia_records"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};")
    op.drop_table("policy_violations")
    op.drop_table("policies")
    op.drop_table("aisia_records")
    op.drop_table("risk_assessments")
