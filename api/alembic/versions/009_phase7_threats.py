"""Phase 7 — Threat Intelligence module.

Adds:
  - threats             Global catalogue of AI threats (admin-maintained).
  - modules_entitled    Per-tenant licence entitlements (one row per active
                        module SKU). Drives the @requires_module gate.

`threat_exposures`, `mitigation_actions`, `endpoint_agent_events` and
`endpoint_devices` are deferred to Phase 7.3 / 7.6 — this migration only
ships the catalogue + licence-gate tables needed for the first
deployable slice of Phase 7.1.

Threats are global (admin-maintained, no tenant_id, read-only for
tenants). The catalogue is loaded from catalogue/threats/**/*.yaml via
the threats_importer script.

Revision ID: 009_phase7_threats
Revises: 008_compliance_verbatim
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_phase7_threats"
down_revision: Union[str, None] = "008_compliance_verbatim"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ threats (global) ============
    op.create_table(
        "threats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("threat_id", sa.String(64), unique=True, nullable=False,
                  comment="Stable catalogue ID, e.g. AEGIS-T-0001"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False,
                  comment="Verbatim authoritative citation"),
        sa.Column("verbatim_description", sa.Text(), nullable=False,
                  comment="Description quoted verbatim from upstream source"),
        sa.Column("description", sa.Text(), nullable=True,
                  comment="AEGIS operational interpretation"),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("classes",  postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column("vectors",  postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column("mitre_atlas_ids", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("owasp_llm_ids",   postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("sector_amplifiers", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("applies_to_jurisdictions", postgresql.ARRAY(sa.String(8)), nullable=True),
        sa.Column("exposure_check", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mitigation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_hints", postgresql.ARRAY(sa.String(300)), nullable=True),
        sa.Column("compliance_implications", postgresql.ARRAY(sa.String(64)), nullable=True),
        sa.Column("catalogue_version", sa.String(32), nullable=False),
        sa.Column("last_updated", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')",
            name="ck_threats_severity",
        ),
    )
    op.execute(
        "CREATE TRIGGER tg_threats_updated_at BEFORE UPDATE ON threats "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.create_index("ix_threats_severity", "threats", ["severity"])
    op.execute(
        "CREATE INDEX ix_threats_classes_gin ON threats USING GIN (classes);"
    )
    op.execute(
        "CREATE INDEX ix_threats_vectors_gin ON threats USING GIN (vectors);"
    )

    # ============ modules_entitled (per-tenant licence) ============
    op.create_table(
        "modules_entitled",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_sku", sa.String(64), nullable=False,
                  comment="e.g. AEGIS-CORE, AEGIS-COMPLIANCE, AEGIS-THREAT, "
                          "AEGIS-EA, AEGIS-SECTOR-BFSI"),
        sa.Column("edition", sa.String(64), nullable=True,
                  comment="Bundle name, e.g. AEGIS-ENTERPRISE"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("valid_to",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("feature_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("licence_fingerprint", sa.String(64), nullable=True,
                  comment="SHA-256 of the signed licence JSON that activated this row"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "module_sku", name="uq_entitlements_tenant_module"),
    )
    op.execute(
        "CREATE TRIGGER tg_entitlements_updated_at BEFORE UPDATE ON modules_entitled "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.execute(
        "ALTER TABLE modules_entitled ENABLE ROW LEVEL SECURITY;"
    )
    op.execute(
        "CREATE POLICY tenant_isolation ON modules_entitled "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.create_index("ix_modules_entitled_tenant", "modules_entitled", ["tenant_id"])

    # Seed the default dev tenant with every module enabled in dev mode.
    # Production licences override these rows at startup; the dev seed lets
    # `make up` work end-to-end without a licence file.
    op.execute("""
        INSERT INTO modules_entitled (tenant_id, module_sku, edition, feature_flags)
        SELECT
          '00000000-0000-0000-0000-000000000001'::uuid,
          sku,
          'AEGIS-DEV-ALL',
          '{"dev_mode": true}'::jsonb
        FROM (VALUES
          ('AEGIS-CORE'),
          ('AEGIS-COMPLIANCE'),
          ('AEGIS-THREAT'),
          ('AEGIS-EA'),
          ('AEGIS-SECTOR-BFSI'),
          ('AEGIS-SECTOR-INSURANCE'),
          ('AEGIS-SECTOR-CAPITAL-MARKETS')
        ) AS skus(sku)
        ON CONFLICT (tenant_id, module_sku) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("modules_entitled")
    op.execute("DROP INDEX IF EXISTS ix_threats_vectors_gin;")
    op.execute("DROP INDEX IF EXISTS ix_threats_classes_gin;")
    op.drop_table("threats")
