"""Phase 1 — AI Service Catalogue + AI System Registry.

Revision ID: 002_catalogue_registry
Revises: 001_initial
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_catalogue_registry"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Weight table mirrored in app/services/completeness.py — keep both in sync.
COMPLETENESS_SQL = r"""
CREATE OR REPLACE FUNCTION compute_ai_system_completeness(s ai_systems)
RETURNS smallint AS $$
DECLARE total int := 0;
BEGIN
    IF s.intended_purpose       IS NOT NULL AND length(s.intended_purpose) > 0 THEN total := total + 15; END IF;
    IF s.owner_user_id          IS NOT NULL                                     THEN total := total + 10; END IF;
    IF s.department_id          IS NOT NULL                                     THEN total := total + 10; END IF;
    IF s.data_types_processed   IS NOT NULL AND array_length(s.data_types_processed,1) > 0 THEN total := total + 10; END IF;
    IF s.affected_data_subjects IS NOT NULL AND array_length(s.affected_data_subjects,1) > 0 THEN total := total + 10; END IF;
    IF s.deployment_type        IS NOT NULL                                     THEN total := total + 5;  END IF;
    IF s.first_deployed_at      IS NOT NULL                                     THEN total := total + 5;  END IF;
    IF s.human_oversight_desc   IS NOT NULL AND length(s.human_oversight_desc) > 0 THEN total := total + 10; END IF;
    IF s.output_type            IS NOT NULL                                     THEN total := total + 5;  END IF;
    IF s.eu_ai_act_category     IS NOT NULL                                     THEN total := total + 5;  END IF;
    IF s.geographic_scope       IS NOT NULL AND array_length(s.geographic_scope,1) > 0 THEN total := total + 5; END IF;
    IF s.user_population        IS NOT NULL AND length(s.user_population) > 0   THEN total := total + 5;  END IF;
    IF s.aisia_status           IS NOT NULL AND s.aisia_status <> 'not_started' THEN total := total + 5;  END IF;
    RETURN LEAST(total, 100)::smallint;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION ai_systems_recompute_completeness()
RETURNS TRIGGER AS $$
BEGIN
    NEW.completeness_score := compute_ai_system_completeness(NEW);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # ============ ai_services (global catalogue) ============
    op.create_table(
        "ai_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("catalogue_id", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_providers.id"), nullable=True),
        sa.Column("provider_slug", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subcategory", sa.String(120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("api_patterns", postgresql.ARRAY(sa.String(200)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("browser_domains", postgresql.ARRAY(sa.String(200)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("entra_app_ids", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("eu_ai_act_cat", sa.String(32), nullable=True),
        sa.Column("capabilities", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("input_types", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("output_types", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("hq_country", sa.String(2), nullable=True),
        sa.Column("gdpr_applicable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("risk_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("catalogue_version", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ai_services_category", "ai_services", ["category"])
    op.create_index("idx_ai_services_provider", "ai_services", ["provider_id"])
    op.create_index("idx_ai_services_active", "ai_services", ["is_active"],
                    postgresql_where=sa.text("is_active = true"))
    op.execute(
        "CREATE INDEX idx_ai_services_fts ON ai_services USING gin("
        "to_tsvector('english', name || ' ' || COALESCE(description,'')));"
    )
    # GIN indexes for catalogue lookup (domain/pattern matching is hot in Phase 2 ingest).
    op.execute("CREATE INDEX idx_ai_services_api_patterns    ON ai_services USING gin(api_patterns);")
    op.execute("CREATE INDEX idx_ai_services_browser_domains ON ai_services USING gin(browser_domains);")
    op.execute("CREATE INDEX idx_ai_services_entra_app_ids   ON ai_services USING gin(entra_app_ids);")

    op.execute("CREATE TRIGGER tg_ai_services_updated_at BEFORE UPDATE ON ai_services "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")

    # ============ ai_systems (tenant-scoped registry — ISO 42001 Clause 4) ============
    op.create_table(
        "ai_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),

        # Identity
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("internal_alias", sa.String(255), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("catalogue_service_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_services.id"), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_providers.id"), nullable=True),
        sa.Column("provider_name_freetext", sa.String(255), nullable=True),

        # Classification
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subcategory", sa.String(120), nullable=True),
        sa.Column("deployment_type", sa.String(32), nullable=False, server_default="cloud_saas"),
        sa.Column("deployment_env", sa.String(32), nullable=False, server_default="production"),

        # ISO 42001 Clause 4 mandatory fields
        sa.Column("intended_purpose", sa.Text(), nullable=True),
        sa.Column("actual_use_observed", sa.Text(), nullable=True),
        sa.Column("user_population", sa.String(255), nullable=True),
        sa.Column("affected_data_subjects", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("data_types_processed", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("output_type", sa.String(64), nullable=True),
        sa.Column("human_oversight_desc", sa.Text(), nullable=True),
        sa.Column("geographic_scope", postgresql.ARRAY(sa.String(2)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),

        # Ownership
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("business_unit", sa.String(120), nullable=True),

        # Lifecycle
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("first_deployed_at", sa.Date(), nullable=True),
        sa.Column("decommission_date", sa.Date(), nullable=True),

        # Discovery metadata
        sa.Column("discovery_sources", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_shadow", sa.Boolean(), nullable=False, server_default=sa.false()),

        # Risk
        sa.Column("current_risk_score", sa.SmallInteger(), nullable=True),
        sa.Column("risk_level", sa.String(16),
                  sa.Computed(
                      "CASE WHEN current_risk_score >= 75 THEN 'critical' "
                      "WHEN current_risk_score >= 50 THEN 'high' "
                      "WHEN current_risk_score >= 25 THEN 'medium' "
                      "WHEN current_risk_score IS NOT NULL THEN 'low' END",
                      persisted=True)),
        sa.Column("last_risk_assessed_at", sa.DateTime(timezone=True), nullable=True),

        # Compliance
        sa.Column("aisia_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("aisia_impact_level", sa.String(16), nullable=True),
        sa.Column("eu_ai_act_category", sa.String(32), nullable=True),
        sa.Column("policy_status", sa.String(32), nullable=False, server_default="allow"),
        sa.Column("compliance_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),

        # Completeness — set by trigger from compute_ai_system_completeness()
        sa.Column("completeness_score", sa.SmallInteger(), nullable=False, server_default="0"),

        # Metadata
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("custom_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),

        sa.CheckConstraint(
            "current_risk_score IS NULL OR current_risk_score BETWEEN 0 AND 100",
            name="ck_ai_systems_risk_score_range",
        ),
        sa.CheckConstraint(
            "completeness_score BETWEEN 0 AND 100",
            name="ck_ai_systems_completeness_range",
        ),
    )
    op.create_index("idx_ai_systems_tenant", "ai_systems", ["tenant_id"])
    op.create_index("idx_ai_systems_tenant_risk", "ai_systems", ["tenant_id", "risk_level"])
    op.create_index("idx_ai_systems_tenant_status", "ai_systems", ["tenant_id", "status"])
    op.create_index("idx_ai_systems_category", "ai_systems", ["tenant_id", "category"])
    op.create_index("idx_ai_systems_shadow", "ai_systems", ["tenant_id", "is_shadow"],
                    postgresql_where=sa.text("is_shadow = true"))
    op.execute(
        "CREATE INDEX idx_ai_systems_fts ON ai_systems USING gin("
        "to_tsvector('english', name || ' ' || COALESCE(intended_purpose,'') || ' ' "
        "|| COALESCE(internal_alias,'')));"
    )
    op.execute("CREATE TRIGGER tg_ai_systems_updated_at BEFORE UPDATE ON ai_systems "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")

    # Completeness scoring (computed in plpgsql, refreshed on every write).
    op.execute(COMPLETENESS_SQL)
    op.execute(
        "CREATE TRIGGER tg_ai_systems_completeness BEFORE INSERT OR UPDATE ON ai_systems "
        "FOR EACH ROW EXECUTE FUNCTION ai_systems_recompute_completeness();"
    )

    # RLS — tenant isolation
    op.execute("ALTER TABLE ai_systems ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_ai_systems ON ai_systems "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_ai_systems ON ai_systems;")
    op.execute("DROP TRIGGER IF EXISTS tg_ai_systems_completeness ON ai_systems;")
    op.execute("DROP FUNCTION IF EXISTS ai_systems_recompute_completeness();")
    op.execute("DROP FUNCTION IF EXISTS compute_ai_system_completeness(ai_systems);")
    op.drop_table("ai_systems")
    op.drop_table("ai_services")
