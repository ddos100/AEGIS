"""Seed the dev tenant + department so the Keycloak admin user (whose
``tenant_id`` attribute is hard-coded as ``00000000-0000-0000-0000-000000000001``
in ``infra/docker/keycloak-realm/aegis-realm.json``) can actually do anything.

Without this row, every tenant-scoped INSERT fails the foreign key on
``tenants(id)`` and the API returns 500 — most visibly when the first
real ingest event tries to auto-create a shadow ``ai_systems`` row.

Idempotent: uses ``ON CONFLICT DO NOTHING``, safe to run on existing
databases.

In production, tenants are provisioned through the onboarding workflow
(coming in Phase 5); this migration only seeds the dev tenant.

Revision ID: 004_seed_dev_tenant
Revises: 003_discovery_pipeline
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "004_seed_dev_tenant"
down_revision: Union[str, None] = "003_discovery_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Dev tenant — slug matches what the seed Keycloak admin sees.
    op.execute(f"""
        INSERT INTO tenants (id, name, slug, plan, settings, is_active)
        VALUES ('{DEV_TENANT_ID}', 'AEGIS Dev Tenant', 'aegis-dev', 'enterprise',
                '{{"seeded_by": "alembic_004"}}'::jsonb, true)
        ON CONFLICT (id) DO NOTHING;
    """)

    # A default "Security" department so the registry quick-add wizard has
    # something to point at without manual setup.
    op.execute(f"""
        INSERT INTO departments (id, tenant_id, name)
        VALUES ('00000000-0000-0000-0000-000000000010',
                '{DEV_TENANT_ID}',
                'Security')
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(f"DELETE FROM departments WHERE tenant_id = '{DEV_TENANT_ID}';")
    op.execute(f"DELETE FROM tenants WHERE id = '{DEV_TENANT_ID}';")
