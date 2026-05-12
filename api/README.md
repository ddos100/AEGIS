# AEGIS API

FastAPI backend for AEGIS — AI Enterprise Governance & Inventory System.

This is the Python package referenced as `aegis-api` in `pyproject.toml`. Top-level
project documentation lives in the [repository README](../README.md).

## Layout

```
api/
├─ app/
│  ├─ core/           Config, auth (Keycloak JWT), DB session (RLS-aware), logging
│  ├─ models/         SQLAlchemy ORM models (one file per entity)
│  ├─ routes/         FastAPI routers (one file per resource)
│  ├─ services/       Business logic (risk_engine, policy_engine, …) — Phase 4+
│  ├─ workers/        Celery app + tasks
│  ├─ integrations/   External connectors (entra, okta, aws, azure, gcp, m365, network log normalizers, …)
│  └─ main.py         FastAPI entrypoint
├─ alembic/           Hand-written migrations (no autogenerate)
├─ tests/             pytest suite (unit + integration)
├─ pyproject.toml     Project metadata + dependencies
├─ Dockerfile         Production-ish container image
└─ .env.example       Environment template
```

## Local development

From the **repository root** (not from `api/`):

```bash
docker compose up -d api worker beat       # start API + Celery
docker compose exec api alembic upgrade head
docker compose exec api pytest -q
docker compose exec api ruff check .
```

## Key conventions

- **Multi-tenancy via RLS.** Every tenant-scoped table has a `tenant_id` column and an RLS policy. Each request flows through `app.core.database.session_scope(tenant_id=…)`, which sets `app.current_tenant`. Never bypass.
- **Migrations are hand-written.** No `--autogenerate` — Alembic cannot infer RLS policies, triggers, TimescaleDB hypertables, or GIN/partial indexes.
- **Async everywhere.** All DB I/O uses `asyncpg`. Sync code is reserved for Alembic migrations and Celery task bodies (where the work is CPU-bound).
- **Structured logging.** `structlog` with `tenant_id`, `user_id`, and `request_id` in every line. Never log credentials, integration tokens, or raw integration payloads.

See [`CLAUDE.md`](../CLAUDE.md) at the repo root for the full convention list.

## Licence

Proprietary — © Securisti Consulting LLP. All rights reserved.
