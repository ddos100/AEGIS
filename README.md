# AEGIS — AI Enterprise Governance & Inventory System

AI Security Posture Management (AI-SPM) platform by **Securisti Consulting LLP**.

AEGIS discovers every AI system in an enterprise — web apps, browser extensions,
desktop agents, cloud AI services, embedded SaaS AI features, and code-level AI
SDK usage — classifies them by risk, enforces acceptable-use policies, and maps
compliance to ISO 42001, EU AI Act, NIST AI RMF, DPDPA, RBI, IRDAI, and SEBI.

> **Status:** Phase 2 — Discovery Engine: network telemetry + browser extension live (May 2026).

## Prerequisites

Before installing, ensure the following are available on your machine:

| Tool | Version | Purpose |
|------|---------|---------|
| **Git** | 2.40+ | Clone the repository |
| **Docker Desktop** | 4.x (Compose v2) | Runs the full local stack |
| **Python** | 3.12 (via [pyenv](https://github.com/pyenv/pyenv) recommended) | Local API development & catalogue tooling |
| **Node.js** | 20 LTS (via [nvm](https://github.com/nvm-sh/nvm)) | Web app & extension builds |
| **make** | any | Convenience targets (`make up`, `make test`, etc.) |
| **`uv`** (optional) | latest | Faster Python dependency installs |
| **pnpm** (optional) | 9.x | Faster web dependency installs |

On Windows use **Git Bash**, **WSL2**, or **PowerShell**. The `Makefile` requires a bash-compatible shell.

## Install from git

### 1. Clone the repository

```bash
# HTTPS
git clone https://github.com/ddos100/AEGIS.git aegis
cd aegis

# Or SSH (if your key is registered on GitHub)
git clone git@github.com:ddos100/AEGIS.git aegis
cd aegis
```

### 2. Configure environment

```bash
cp api/.env.example api/.env
```

Edit `api/.env` and replace the placeholders for these two values **before exposing any service**:

```bash
# Generate a real Fernet key for integration-credential encryption
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → paste output into FERNET_KEY in api/.env

# Rotate INGEST_API_KEY in api/.env to a strong random value
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` is gitignored — never commit a populated copy.

### 3. Start the full stack

```bash
docker compose up -d            # postgres+TimescaleDB, redis, keycloak, api, worker, beat, web
docker compose ps               # confirm every service is healthy
docker compose logs -f api      # tail API logs (Ctrl+C to detach)
```

First boot takes 1–3 minutes while Docker pulls the Postgres+TimescaleDB and Keycloak images.

### 4. Apply database migrations

```bash
docker compose exec api alembic upgrade head
```

You should see `Running upgrade  -> 001_initial`. This creates `tenants`, `users`, `departments`, `ai_providers`, the append-only `audit_log`, all RLS policies, and the `updated_at` triggers.

### 5. Seed the AI Service Catalogue

The 29 reference YAML services in `catalogue/services/` are imported into the
`ai_services` and `ai_providers` tables on demand:

```bash
make catalogue-import
# or:
docker compose exec api python /workspace/catalogue/scripts/importer.py -v
```

The importer is idempotent — re-running upserts rows by `catalogue_id`.

### 6. Verify the install

| Check | Command / URL | Expected |
|-------|---------------|----------|
| API health | `curl http://localhost:8000/v1/health` | `{"status":"ok","version":"0.1.0","db":"ok",...}` |
| OpenAPI docs | http://localhost:8000/docs | Swagger UI loads |
| Web dashboard | http://localhost:5173 | AEGIS overview page with "API: ok" badge |
| Keycloak admin | http://localhost:8080 (admin / admin) | Admin console loads; `aegis` realm visible |
| Celery beat | `docker compose logs beat` | `heartbeat` task firing every minute |

### 7. Run the tests

```bash
docker compose exec api pytest -q          # API tests
docker compose exec api ruff check .       # Lint
cd web && npm install && npm run typecheck # Web type-check (one-time install)
```

### 8. Send a sample log batch (Phase 2 sanity check)

```bash
# Replace TENANT_ID with the UUID from your tenants table and INGEST_KEY with api/.env
curl -sX POST http://localhost:8000/v1/ingest/network \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Key: ${INGEST_KEY:-dev-ingest-key-change-me}" \
  -d '{
    "source": "zscaler_nss",
    "tenant_id": "'$TENANT_ID'",
    "events": [
      {"user":"alice@example.com","department":"Eng","url":"https://chat.openai.com/v1/chat/completions","cip":"10.0.1.5","time":1715600000,"reqsize":1234,"respsize":4567}
    ]
  }'
# → {"accepted":1,"queued":false,"matched":1,"shadow_new":1}
```

The new shadow AI system is now visible at `/registry` and `/discovery` in the web app.

### 9. Validate the AI service catalogue (schema-only, no DB writes)

```bash
cd catalogue
pip install pyyaml jsonschema
python -m scripts.validate                  # all seed YAML files must validate
```

### Common operations (via Makefile)

```bash
make up                  # docker compose up -d
make down                # docker compose down (volumes preserved)
make destroy             # docker compose down -v (destroys volumes — careful)
make logs                # tail every service
make migrate             # apply migrations
make makemigration MSG="add policies table"  # create a new revision
make test                # run API tests inside the container
make lint fmt typecheck  # quality gates
make catalogue-validate  # JSON-Schema validate every catalogue YAML
```

### Updating after `git pull`

```bash
git pull                                                          # fetch latest changes
docker compose build api worker beat                              # rebuild images if Dockerfile/deps changed
docker compose up -d                                              # restart with new images
docker compose exec api alembic upgrade head                      # apply any new migrations
cd web && npm install                                             # if web/package.json changed
```

### Troubleshooting

- **`docker compose up` fails with port conflict** — another service is bound to 5432 / 6379 / 8000 / 5173 / 8080. Stop the offending process or remap the host-side port in `docker-compose.yml`.
- **API exits immediately on first boot** — wait ~10s after `docker compose up`; the API entrypoint runs `alembic upgrade head` and won't start serving until Postgres is healthy. Re-run `docker compose up -d` if it raced ahead of Postgres.
- **Keycloak admin login fails** — the dev realm uses `admin` / `admin`. This is for local development only; rotate before any non-local deployment.
- **`pytest` fails with tenant_id / RLS errors** — RLS is active; all integration tests must use the `fake_user` fixture which sets the tenant context. See [`api/tests/conftest.py`](api/tests/conftest.py).
- **Catalogue YAML validation errors in CI** — run `python -m catalogue.scripts.validate` locally; the error output points to the file and JSON path that failed.

## Quickstart (one-liner, for impatient evaluators)

```bash
git clone https://github.com/ddos100/AEGIS.git aegis && cd aegis && \
  cp api/.env.example api/.env && docker compose up -d && \
  sleep 30 && docker compose exec api alembic upgrade head && \
  curl http://localhost:8000/v1/health
```

## Repository layout

```
aegis/
├─ api/         FastAPI backend (Python 3.12, async SQLAlchemy, Celery)
├─ web/         React + TypeScript + Tailwind dashboard
├─ extension/   Chrome MV3 extension — Shadow AI detector
├─ agent/       Endpoint agent (Phase 3+)
├─ catalogue/   AI Service Catalogue (YAML) + validation tooling
├─ infra/       Docker Compose, Helm, Terraform
└─ .github/     CI workflows
```

## Architecture — six layers

1. **Discovery Engine** — 7 vectors: Network telemetry (Proxy/CASB/NGFW/DNS/XDR/EDR — 20+ vendor connectors), Browser extension (MV3), Endpoint agent, Identity provider (Entra ID/Okta), Cloud AI (AWS/Azure/GCP), SaaS audit (M365 Copilot, Google Workspace), Code repositories.
2. **AI System Registry** — ISO 42001 Clause 4 register, auto-populated by discovery, with 20 canonical fields per system.
3. **Risk Assessment Engine** — 5-dimension weighted scoring (data sensitivity, AI capability, regulatory exposure, access scope, provider trust), daily recalculation, AISIA workflow.
4. **Policy Engine** — Rule evaluation in priority order: Allow / Monitor / Alert / Block / Require Approval.
5. **Compliance Module** — Mapping to ISO 42001, EU AI Act, NIST AI RMF, DPDPA, RBI, IRDAI, SEBI; audit-ready evidence packs.
6. **Dashboard & Reporting** — AI Ecosystem Map (D3 force graph), Shadow AI Radar, Risk Posture, Executive PDFs.

## Phase roadmap

| Phase | Weeks | Outcome |
|-------|-------|---------|
| 0 — Foundation | 1–3 | Monorepo, DB schema, FastAPI skeleton, Keycloak auth, CI/CD |
| 1 — Catalogue + Registry | 4–6 | 500+ catalogue entries, ISO 42001 AI System Registry CRUD |
| 2 — Network + Browser Discovery | 7–12 | 20+ vendor log connectors, Chrome MV3 extension live |
| 3 — IdP + Cloud + SaaS Discovery | 13–18 | Entra ID, Okta, AWS, Azure, GCP, M365 Copilot |
| 4 — Risk + Policy Engine | 19–24 | 5-dimension scoring, AISIA workflow, policy rules |
| 5 — Compliance + Dashboard | 25–32 | 7 frameworks, D3 Ecosystem Map, executive PDFs, Eramba |

## Tech stack

| Component | Technology |
|-----------|-----------|
| API Backend | Python 3.12 / FastAPI / async SQLAlchemy |
| Task Queue | Celery + Redis |
| Primary DB | PostgreSQL 16 + TimescaleDB (RLS multi-tenancy) |
| Frontend | React 18 + TypeScript + Tailwind + ShadCN/UI |
| Browser Extension | Chrome MV3 (Edge-compatible) |
| AI/ML | Claude API (`claude-sonnet-4-6`) + Ollama (on-premise) |
| Auth | Keycloak (OIDC/SAML federation) |
| Orchestration | n8n (self-hosted) |
| Infrastructure | Docker Compose (dev) · Kubernetes + Helm (prod) |
| CI/CD | GitHub Actions |

## Licence

Proprietary — © Securisti Consulting LLP. All rights reserved.
