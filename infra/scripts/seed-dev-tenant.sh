#!/usr/bin/env bash
# Idempotently insert the default dev tenant matching the JWT seeded in
# infra/docker/keycloak-realm/aegis-realm.json (tenant_id attribute on
# admin@aegis.local).
#
# Required before the real ingest path will succeed — ai_systems has a
# foreign key on tenants(id), so without this row inserts will fail with
# a FK violation. The Test broadcast button works without it (it only
# publishes to Redis), but real ingest does not.

set -euo pipefail

TENANT_ID=${TENANT_ID:-00000000-0000-0000-0000-000000000001}
TENANT_NAME=${TENANT_NAME:-Default Dev Tenant}
TENANT_SLUG=${TENANT_SLUG:-default}

docker compose exec -T postgres psql -U aegis -d aegis -v ON_ERROR_STOP=1 <<SQL
INSERT INTO tenants (id, name, slug, plan, is_active)
VALUES ('${TENANT_ID}', '${TENANT_NAME}', '${TENANT_SLUG}', 'discovery', true)
ON CONFLICT (id) DO NOTHING;

SELECT id, name, slug, plan FROM tenants WHERE id = '${TENANT_ID}';
SQL
