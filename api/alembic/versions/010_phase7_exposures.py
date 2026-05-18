"""Phase 7.1 — Threat exposure verdicts.

Adds:
  - threat_exposures   Per-tenant verdict per threat, with explanation +
                       evidence. Status one of:
                         exposed | not_exposed | unknown | mitigated.
                       The engine guarantees no exposure is left undefined
                       — `unknown` is an explicit state with reasons
                       naming the missing telemetry source.

The mitigation_actions table is deferred to Phase 7.4 (orchestrator).
The endpoint_agent_events / endpoint_devices tables are deferred to
Phase 7.6.

Revision ID: 010_phase7_exposures
Revises: 009_phase7_threats
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_phase7_exposures"
down_revision: Union[str, None] = "009_phase7_threats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "threat_exposures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("threat_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("threats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  comment="exposed | not_exposed | unknown | mitigated"),
        sa.Column("reasons", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default=sa.text("ARRAY[]::text[]"),
                  comment="Pipe-style PREDICATE: VERDICT — observation lines"),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.String(300)), nullable=False,
                  server_default=sa.text("ARRAY[]::varchar[]"),
                  comment="Machine-readable evidence pointers"),
        sa.Column("missing_telemetry", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("ARRAY[]::varchar[]"),
                  comment="Telemetry sources that would unblock an unknown verdict"),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('exposed','not_exposed','unknown','mitigated')",
            name="ck_threat_exposures_status",
        ),
        sa.UniqueConstraint("tenant_id", "threat_id", name="uq_threat_exposures_unique"),
    )
    op.execute(
        "CREATE TRIGGER tg_threat_exposures_updated_at BEFORE UPDATE ON threat_exposures "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.execute(
        "ALTER TABLE threat_exposures ENABLE ROW LEVEL SECURITY;"
    )
    op.execute(
        "CREATE POLICY tenant_isolation ON threat_exposures "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.create_index("ix_threat_exposures_tenant_status", "threat_exposures",
                    ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("threat_exposures")
