"""Phase 7.4 — Mitigation orchestrator (propose-only).

Adds:
  - mitigation_actions   Append-only history of proposed / approved /
                         applied / verified / drifted / rolled-back
                         mitigations. One row per (tenant, threat,
                         mitigation step) on each recompute cycle.

Behaviour shipped with this migration:
  - The orchestrator service creates rows with status='proposed' when a
    threat exposure verdict is 'exposed'. NOTHING IS PUSHED to vendor
    APIs in this phase — propose-only is the locked v1 default per
    PHASE-7-PLAN.md §3 ("Mitigation default posture: configurable per
    client; propose-only across the board at GA").
  - The 'queued' / 'applied' / 'verified' / 'drifted' states wire up in
    Phase 7.5 once the per-integration push adapters land.

Idempotency
  - `idempotency_key` is computed by the orchestrator as a stable hash
    of (tenant_id, threat_id, integration, action, JSON-canonicalised
    params). Repeat orchestrator runs over the same exposed state
    produce no new rows.
  - Existing rows in terminal states (rejected, applied, verified,
    rolled_back) are NEVER overwritten — orchestrator only refreshes
    'proposed' rows whose params changed.

Revision ID: 011_phase74_mitigations
Revises: 010_phase7_exposures
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_phase74_mitigations"
down_revision: Union[str, None] = "010_phase7_exposures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mitigation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("threat_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("threats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exposure_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("threat_exposures.id", ondelete="SET NULL"),
                  nullable=True),
        # Mitigation step identification --------------------------------
        sa.Column("integration", sa.String(64),  nullable=False,
                  comment="e.g. zscaler, palo_alto, crowdstrike, cloudflare_gateway, "
                          "chrome_enterprise, aegis_endpoint_agent"),
        sa.Column("action", sa.String(120), nullable=False,
                  comment="Vendor-side primitive name, e.g. block_url_category"),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("severity_min", sa.String(16), nullable=True),
        sa.Column("requires_module", sa.String(64), nullable=True),
        sa.Column("preference", sa.String(16), nullable=False, server_default="preferred",
                  comment="preferred | alternate"),
        sa.Column("idempotency_key", sa.String(64), nullable=False,
                  comment="sha256(tenant|threat|integration|action|params canonical)"),
        # Lifecycle ---------------------------------------------------
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed",
                  comment="proposed | rejected | dismissed | queued | applied | "
                          "verified | drifted | rolled_back | failed"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("proposed_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("approved_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error",   sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('proposed','rejected','dismissed','queued','applied',"
            "'verified','drifted','rolled_back','failed')",
            name="ck_mitigation_actions_status",
        ),
        sa.CheckConstraint(
            "preference IN ('preferred','alternate')",
            name="ck_mitigation_actions_preference",
        ),
        sa.UniqueConstraint("tenant_id", "idempotency_key",
                            name="uq_mitigation_actions_idempotency"),
    )
    op.execute(
        "CREATE TRIGGER tg_mitigation_actions_updated_at BEFORE UPDATE ON mitigation_actions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.execute("ALTER TABLE mitigation_actions ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation ON mitigation_actions "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.create_index("ix_mitigation_actions_tenant_status",
                    "mitigation_actions", ["tenant_id", "status"])
    op.create_index("ix_mitigation_actions_threat",
                    "mitigation_actions", ["threat_id"])


def downgrade() -> None:
    op.drop_table("mitigation_actions")
