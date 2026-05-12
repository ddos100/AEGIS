# AEGIS — AI Enterprise Governance & Inventory System

AI Security Posture Management (AI-SPM) platform by **Securisti Consulting LLP**.

AEGIS discovers every AI system in an enterprise — web apps, browser extensions,
desktop agents, cloud AI services, embedded SaaS AI features, and code-level AI
SDK usage — classifies them by risk, enforces acceptable-use policies, and maps
compliance to ISO 42001, EU AI Act, NIST AI RMF, DPDPA, RBI, IRDAI, and SEBI.

> **Status:** Phase 0 — Foundation (scaffolded May 2026).

## Quickstart

```bash
# 1. Copy environment template
cp api/.env.example api/.env

# 2. Start the full stack
docker compose up -d

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. Sanity check
curl http://localhost:8000/v1/health      # API
open http://localhost:5173                # Web UI
open http://localhost:8080                # Keycloak admin (admin/admin)
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
