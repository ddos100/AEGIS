"""Phase 3 — IdP + Cloud + SaaS discovery tables.

Adds:
  - integration_credentials  Encrypted credentials (Fernet) for every external
                             system AEGIS talks to (Entra ID, Okta, AWS, Azure,
                             GCP, M365, Salesforce, Google Workspace, …).
  - idp_users                Identity records pulled from the IdP, mapped to
                             AEGIS users by email.
  - oauth_grants             OAuth2 application grants observed in the IdP —
                             the principal "Vector 4" discovery output.
  - cloud_ai_resources       AI service inventory from cloud control planes
                             (AWS Bedrock, Azure OpenAI, Vertex AI, etc).

All four tables are tenant-scoped with RLS.

Revision ID: 005_phase3_integrations
Revises: 004_seed_dev_tenant
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_phase3_integrations"
down_revision: Union[str, None] = "004_seed_dev_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ integration_credentials ============
    op.create_table(
        "integration_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration", sa.String(64), nullable=False),  # entra_id | okta | aws | azure | gcp | m365 | google_workspace | salesforce
        sa.Column("kind", sa.String(16), nullable=False),         # idp | cloud | saas
        sa.Column("name", sa.String(255), nullable=False),
        # Fernet ciphertext of the JSON-serialised credentials map. Decryption
        # is done in the application layer (app.core.crypto). DB never sees
        # the cleartext — no need for a DB-side decrypt function.
        sa.Column("credentials_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scopes", postgresql.ARRAY(sa.String(255)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),  # active|paused|error|expired
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "integration", "name", name="uq_credentials_name"),
    )
    op.create_index("idx_credentials_tenant", "integration_credentials", ["tenant_id"])
    op.create_index("idx_credentials_status", "integration_credentials",
                    ["tenant_id", "status"])
    op.execute("CREATE TRIGGER tg_credentials_updated_at BEFORE UPDATE ON integration_credentials "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("ALTER TABLE integration_credentials ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_credentials ON integration_credentials "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ idp_users ============
    op.create_table(
        "idp_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("integration_credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idp_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("idp_groups", postgresql.ARRAY(sa.String(255)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("aegis_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "integration_id", "idp_user_id",
                            name="uq_idp_users_unique"),
    )
    op.create_index("idx_idp_users_tenant", "idp_users", ["tenant_id"])
    op.create_index("idx_idp_users_email", "idp_users", ["tenant_id", "email"])
    op.execute("ALTER TABLE idp_users ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_idp_users ON idp_users "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ oauth_grants ============
    op.create_table(
        "oauth_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("integration_credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idp_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("idp_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("app_id", sa.String(255), nullable=False),                # client_id / appId
        sa.Column("app_name", sa.String(255), nullable=False),
        sa.Column("app_publisher", sa.String(255), nullable=True),
        sa.Column("granted_scopes", postgresql.ARRAY(sa.String(255)), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("consent_type", sa.String(16), nullable=True),            # user|admin
        sa.Column("catalogue_match", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("tenant_id", "integration_id", "app_id", "idp_user_id",
                            name="uq_oauth_grants_unique"),
    )
    op.create_index("idx_oauth_grants_tenant", "oauth_grants", ["tenant_id"])
    op.create_index("idx_oauth_grants_match", "oauth_grants",
                    ["tenant_id", "catalogue_match"])
    op.execute("ALTER TABLE oauth_grants ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_oauth_grants ON oauth_grants "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # ============ cloud_ai_resources ============
    op.create_table(
        "cloud_ai_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("integration_credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cloud_provider", sa.String(16), nullable=False),       # aws | azure | gcp
        sa.Column("resource_type", sa.String(64), nullable=False),        # bedrock_model | sagemaker_endpoint | azure_openai_deployment | vertex_endpoint | …
        sa.Column("resource_id", sa.String(512), nullable=False),         # arn / fqid
        sa.Column("resource_name", sa.String(255), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("account_id", sa.String(64), nullable=True),
        sa.Column("project_id", sa.String(255), nullable=True),
        sa.Column("service_name", sa.String(64), nullable=True),          # bedrock | sagemaker | cognitiveservices
        sa.Column("model_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("cost_last_30d", sa.Numeric(12, 2), nullable=True),
        sa.Column("usage_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("catalogue_match", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("tenant_id", "cloud_provider", "resource_id",
                            name="uq_cloud_ai_resources_unique"),
    )
    op.create_index("idx_cloud_resources_tenant", "cloud_ai_resources", ["tenant_id"])
    op.create_index("idx_cloud_resources_provider", "cloud_ai_resources",
                    ["tenant_id", "cloud_provider"])
    op.execute("ALTER TABLE cloud_ai_resources ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY tenant_isolation_cloud_resources ON cloud_ai_resources "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )


def downgrade() -> None:
    for tbl in ("cloud_ai_resources", "oauth_grants", "idp_users", "integration_credentials"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl.replace('_ai_resources','_resources').replace('integration_credentials','credentials')} ON {tbl};")
        op.drop_table(tbl)
