# AEGIS Helm Chart

Deploys the AEGIS AI-SPM platform onto Kubernetes.

```
infra/helm/aegis/
├─ Chart.yaml
├─ values.yaml           # defaults (no secrets)
├─ values.prod.yaml      # production overrides — commit safe
└─ templates/
   ├─ _helpers.tpl
   ├─ api-deployment.yaml      # api + HPA + PDB + Service
   ├─ worker-deployment.yaml   # worker-default, worker-ingest, beat
   ├─ web-deployment.yaml
   ├─ ingress.yaml
   ├─ migrate-job.yaml         # pre-install + pre-upgrade hook
   └─ NOTES.txt
```

## Pre-install — secrets

AEGIS deliberately never creates Kubernetes Secrets. Provision them ahead of
install (via External Secrets Operator pointing at HashiCorp Vault, AWS
Secrets Manager, or GCP Secret Manager) under the names referenced in
`values.yaml -> secrets:` :

| Secret | Required keys |
|--------|---------------|
| `aegis-database` | `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| `aegis-ingest`   | `INGEST_API_KEY` |
| `aegis-fernet`   | `FERNET_KEY` (optional: `FERNET_KEY_PREVIOUS` during a rotation window) |
| `aegis-anthropic` | `ANTHROPIC_API_KEY` (optional — enables Claude narratives) |

## Install

```bash
# 1. From the repo root
helm install aegis ./infra/helm/aegis \
  --namespace aegis-prod --create-namespace \
  -f infra/helm/aegis/values.prod.yaml

# 2. After install, seed the catalogue + frameworks
kubectl exec -n aegis-prod deploy/aegis-aegis-api -- \
  python /workspace/catalogue/scripts/importer.py -v
kubectl exec -n aegis-prod deploy/aegis-aegis-api -- \
  python /workspace/catalogue/scripts/import_frameworks.py -v
```

## Upgrade

```bash
helm upgrade aegis ./infra/helm/aegis \
  --namespace aegis-prod \
  -f infra/helm/aegis/values.prod.yaml
```

The pre-upgrade `migrate-job` runs `alembic upgrade head` before any pod
swap, so the API never starts against an out-of-date schema.

## What this chart deploys

| Workload | Replicas | Autoscale | Notes |
|----------|----------|-----------|-------|
| `api`            | 3 | 3–10 (CPU 60%) | FastAPI, mounted at `/v1` via Ingress |
| `worker-default` | 2 | 2–8            | Default Celery queue |
| `worker-ingest`  | 3 | 3–15           | High-throughput log ingestion |
| `beat`           | 1 | none           | Celery scheduler (singleton; uses `Recreate` strategy) |
| `web`            | 2 | none           | Static React assets served by nginx |

PDB on `api` keeps `minAvailable: 2` during voluntary disruptions.

## Production wiring

- **Postgres** — set `postgres.bundle: false` and point `postgres.host` at an
  external managed instance (RDS Postgres + TimescaleDB enabled, or
  CloudSQL Postgres with the timescaledb extension). The DATABASE_URL
  in `aegis-database` should reference that host.
- **Redis** — same pattern. Elasticache or Memorystore.
- **Keycloak** — already external; set `keycloak.url` + `keycloak.publicUrl`
  in `values.prod.yaml`.
- **Ingress** — defaults assume nginx-ingress + cert-manager. The
  `proxy-read-timeout: 3600` annotation is mandatory for the
  `/v1/ws/discovery` WebSocket; remove it at your peril.

## Helm-templating sanity check

```bash
helm template aegis ./infra/helm/aegis \
  -f infra/helm/aegis/values.prod.yaml \
  --namespace aegis-prod \
  > /tmp/aegis-render.yaml
kubectl apply --dry-run=client -f /tmp/aegis-render.yaml
```
