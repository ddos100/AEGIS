# AEGIS — Claude Code Instructions

## Project
AEGIS (AI Enterprise Governance & Inventory System) — AI-SPM platform by Securisti Consulting LLP (SCLLP).

**Location on disk:** `D:\Backup\Zoho WorkDrive (Securisti Consulting LLP)\My Folders\Claude\aegis`
**Plan:** see the v1.0 implementation plan in `C:\Users\Administrator\Downloads\AEGIS-Implementation-Plan-v1.0.docx` and `C:\Users\Administrator\.claude\plans\c-users-administrator-downloads-aegis-a-jiggly-snowglobe.md`

## Architecture
- `api/`        — FastAPI 3.12, Celery+Redis, PostgreSQL 16 + TimescaleDB
- `web/`        — React 18 + TypeScript + Tailwind (+ ShadCN/UI to be added in Phase 1)
- `extension/`  — Chrome Manifest V3
- `agent/`      — Endpoint agent (Python/Go) — Phase 3+
- `catalogue/`  — AI Service Catalogue YAML (500+ services target)
- `infra/`      — Docker Compose, Helm, Terraform
- `.github/`    — CI workflows

## Conventions
- **DB queries** are tenant-scoped via PostgreSQL RLS. Every request flows through
  `app.core.database.session_scope(tenant_id=...)`, which runs
  `SELECT set_config('app.current_tenant', ?, true)`. Never bypass this.
- **Routes** require `get_current_user()` (and `get_db()` chains tenant context off it).
  Public exceptions: `/v1/health`, ingest endpoints (use `verify_ingest_key`).
- **Migrations** are hand-written Alembic. No `--autogenerate`. Reason: autogenerate
  misses RLS policies, triggers, TimescaleDB hypertables, partial/GIN indexes.
- **Tests**: pytest for API (testcontainers-postgres for integration), vitest for web,
  factory_boy for test data.
- **Errors**: raise `fastapi.HTTPException`; let global handlers serialize.
- **Async**: all DB ops async (asyncpg). All I/O uses async/await.
- **Logging**: structlog with `tenant_id`, `user_id`, `request_id` in every line.
- **Imports**: absolute (`from app.models.ai_provider import AIProvider`).

## Claude API usage rules
- Risk narratives: `claude-sonnet-4-6`, `max_tokens=600`, cache the system prompt.
- AISIA drafts: `claude-sonnet-4-6`, `max_tokens=1000`.
- Strip all PII before sending to Claude API.
- Use `claude-haiku-4-5` for low-stakes tasks (completeness hints, control guidance).

## Running locally
```bash
docker compose up -d                      # full stack
docker compose exec api alembic upgrade head
docker compose exec api pytest -q
cd web && npm run dev                     # or use the dockerised web service
```

## Key files
- `api/app/core/auth.py`           — JWT validation (Keycloak JWKS) + AuthenticatedUser
- `api/app/core/deps.py`           — FastAPI deps: get_db, get_current_user, require_admin, verify_ingest_key
- `api/app/core/database.py`       — Async engine + session_scope (RLS-aware)
- `api/app/models/`                — SQLAlchemy models (one file per entity)
- `api/app/routes/`                — FastAPI routers (one file per resource)
- `api/app/services/`              — Business logic (risk_engine, policy_engine, ... — Phase 4+)
- `api/app/workers/celery_app.py`  — Celery configuration + beat schedule
- `api/alembic/versions/`          — Hand-written migrations
- `catalogue/schemas/service.schema.yaml`  — JSON Schema for AI service entries
- `extension/manifest.json`        — Chrome MV3 manifest
- `extension/src/background/service_worker.js`  — Tab matcher + batch sender

## Phase status
- ✅ Phase 0 — Foundation (this scaffold)
- ⏳ Phase 1 — AI Service Catalogue + Registry CRUD (next)
- ⏳ Phase 2 — Network telemetry + Browser extension discovery
- ⏳ Phase 3 — IdP + Cloud + SaaS discovery
- ⏳ Phase 4 — Risk Assessment + Policy Engine
- ⏳ Phase 5 — Compliance Module + Dashboard + Reports

## Don'ts
- Don't add features beyond the active phase.
- Don't introduce backwards-compat shims for code not yet shipped.
- Don't autogenerate Alembic migrations.
- Don't log credentials, PII, or raw integration tokens.
- Don't query raw `ai_usage_events` from the dashboard — use continuous aggregates only.
