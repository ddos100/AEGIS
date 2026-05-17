# AEGIS — Phase 7: AI Threat Intelligence Module
**Plan-of-record, locked.** Securisti Consulting LLP · 2026-05-18

This document is the merged decision record for Phase 7. It captures every
decision taken across the planning rounds and is the source-of-truth the
engineering team builds against. No code shipped on this branch yet —
this PR scaffolds only the catalogue + plan.

---

## 1 · Branch model

| Branch | Purpose | Rule |
|--------|---------|------|
| `main` | Continuing post-v1.0.0 trunk; v1.0.0 lives here too (tag `v1.0.0`) | Open for stabilisation hotfixes only |
| `release/v1.0.0` | Frozen snapshot of v1.0.0 (commit `7426472`) | Read-only; hotfix branches off this if a v1.0.x is needed |
| `phase-7/threat-intel` | All Phase 7 work | Merge to `main` only at end of Phase 7.6 |

---

## 2 · Locked decisions

### Architecture
- **Threat taxonomy** — 9 access vectors × 14 threat classes; T7.x POSIX expansion is a distinct schema branch with 26 enumerated patterns.
- **Continuous update** — feed ingest from MITRE ATLAS, OWASP LLM Top 10, NIST AI 600-1, OSV.dev, HuggingFace, PyPI, CERT-In, AIID. IT-ISAC AI WG keeps **configurable** — ingest adapter ships, activation gated by tenant feature flag.
- **Catalogue licensing** — Per-module commercial licensing; no open-source/MIT. Modules: `AEGIS-CORE`, `AEGIS-COMPLIANCE`, `AEGIS-THREAT`, `AEGIS-EA`, `AEGIS-SECTOR-*`.
- **Licence signing** — Ed25519 via AWS KMS asymmetric, annual rotation.
- **Determinism** — every threat YAML has `verbatim_description` + `source_ref` + non-empty `exposure_check`. Inventory digest pinned at `catalogue/threats/.inventory_digest`; CI test asserts no drift.

### Endpoint Agent (AEGIS-EA)
- **OS scope day-one** — Linux + macOS + Windows together (Phase 7.6).
- **Language** — Go, single static binary per OS/arch; cosign-signed; SBOM per release.
- **Privileges** — runs as logged-in user; degrades gracefully when admin/EndpointSecurity entitlement absent.
- **Posture** — observe-only default. Enforcement deferred to a post-GA 7.7 increment.

### Mitigation orchestrator
- **Posture model** — configurable per (severity, integration class) cell with tiers `disabled`, `propose`, `propose_with_dry_run`, `auto_apply_after_2p`, `auto_apply`.
- **Default matrix** — propose-only across the board at GA.
- **Pre-condition guards** — `auto_apply` requires ≥30d propose-only history with ≥90% admin-approval rate; critical cells need `break_glass_acknowledged: true`.
- **Verification cadence** — tight: 15 min critical, 1 h high, 6 h medium, 24 h low. Drift escalates with auto fallback to `propose_with_dry_run`.

### Sectoral overlays
- **Resolution** — left-biased base → sector overlay → tenant override. Every merged record carries `provenance`.
- **Day-one sector packs** — BFSI, Insurance, Capital Markets (each as `AEGIS-SECTOR-*` SKU).
- **Customisation** — tenant can add private threats, **tighten** predicates, suppress controls with justification + ≤180d expiry. Cannot loosen below base or edit verbatim text.

### Privacy by Design
- **No PII collected** — AEGIS does not store prompt text, model output, file contents, URL paths, screen contents, keystrokes, voice/video, browser history beyond AI-domain matches, source code, or chat transcripts.
- **Pseudonymous IDs** — `user_id` is a UUID minted by Keycloak; the mapping to email lives only inside Keycloak. Just-in-time `/v1/me/resolve` is audit-logged.
- **EA telemetry** — strict allow-list of event kinds (see §B.3.4 in plan doc). Command-line is **hashed before leaving device**.
- **Domain-only ingest** — path/query stripped at normaliser; DB check-constraint forbids `path`, `query`, `body`, `headers` keys.
- **Encryption** — TLS 1.3 in transit; AWS KMS-wrapped DEKs at rest; Fernet column-level rotation quarterly.
- **DPDPA stance** — AEGIS holds no personal data of Data Principals; customer is not acting as Data Fiduciary *for AEGIS-resident data*. Documented in EULA.
- **Retention** — 90d hot + 1y cold for EA telemetry; tenant exit purges within 30d after 90d read-only grace.

### Commercial / pricing structure
- Dimensions: D1 module SKU · D2 tenant tier · D3 AI systems band · D4 discovery seats band · D5 EA devices band · D6 integrations count · D7 sector packs · D8 support tier · D9 deployment topology.
- Editions: Starter / Growth / Enterprise / Regulated-Plus (in-place upgradable).
- Annual subscription up front; banded true-up at renewal. Numbers set by SCLLP commercial.
- Discount hooks: multi-year commit, ≥3-module bundle. Levers visible to commercial; not enforced at runtime.

---

## 3 · Phasing (15 wk; GA at end of 7.6)

| Phase | Wk | Scope | Exit |
|-------|----|-------|------|
| 7.1 — Catalogue + licence enforcement + overlay merge | 1–3 | Threat YAML schema, validator, digest, ≥30 seed threats, licence file loader, overlay merge engine | Validator + digest pass; entitlement gate returns 402 for unlicensed modules |
| 7.2 — Feed ingest + admin review | 4–5 | ATLAS / OWASP / AIID / OSV / HF / CERT-In normalisers; review queue UI; Claude-assisted draft only | Hourly beat ingests ≥5 sources without error |
| 7.3 — Exposure engine | 6–8 | Predicates over Registry/integrations (no EA yet); per-tenant `threat_exposures`; UI detail w/ reasons + evidence | Every threat resolves to `exposed`/`not_exposed`/`unknown`; unknowns name missing telemetry |
| 7.4 — Mitigation orchestrator (propose) | 9–10 | Per-integration adapters in read+propose-only; approval UI; CAB-ticket auto-create | Propose-only diffs visible for Zscaler, Palo Alto, CrowdStrike, Cloudflare Gateway, Chrome GPO |
| 7.5 — Mitigation push + verify | 11–13 | Apply via integrations; tight verification loop; drift alerts; rollback runbooks | End-to-end block of one synthetic exposed threat verified in dev tenant |
| 7.6 — Endpoint Agent v1 (3 OS) | 14–15 | Go binary, fanotify/EndpointSecurity/ETW backends, npm/pip wrappers (observe-only), MCP scanner, signed enrollment | EA on 1 Linux + 1 macOS + 1 Windows host emits events visible in exposure engine |

Stretch (7.7+): EA enforcement mode, AI-ISAC integration, auto-apply tier rollout, sector packs beyond BFSI/Insurance/Capital Markets.

---

## 4 · Predicate vocabulary (additions beyond compliance auto_check)

Documented at length in the planning round; canonical reference for the
engine to be built in Phase 7.3:

```
any_system_category_in              list[str]
observed_provider_domains           list[str]
observed_provider_jurisdiction      list[ISO-2]
any_system_data_type_in             list[str]
eu_ai_act_category_in               list[str]
m365_copilot_enabled                bool
mcp_server_with_scope               list[str]
endpoint_agent_curl_pipe_sh_within_days        int
endpoint_agent_npm_postinstall_within_days     int
endpoint_agent_pip_setup_hook_within_days      int
endpoint_agent_world_writable_in_ai_path       bool
endpoint_agent_suid_dropped                    bool
endpoint_agent_path_hijack_detected            bool
endpoint_agent_secrets_read_by_ai_proc         bool
endpoint_agent_destructive_cmd_by_ai_proc      bool
dns_query_observed                  list[str]
xdr_process_observed                {name|hash patterns}
idp_oauth_grant_present             list[app_id]
provider_trust_score_below          int
cve_in_runtime                      bool        (OSV match against EA-reported packages)
huggingface_model_in_use            list[str]
aiusage_high_volume_burst           {n, m_minutes}
agentic_mode_observed               bool
cloud_ai_resource_without_guardrail bool
aisia_status_in                     list[str]   (re-used from compliance)
```

Every predicate evaluator emits the same `EvaluationResult(satisfied, reasons,
evidence_refs)` shape the Compliance engine already uses, so the UI panel
pattern is identical.

---

## 5 · Schema additions (sketch — Phase 7.1 builds)

```
threats(id, threat_id UNIQUE, title, severity, classes[], vectors[],
        mitre_atlas_ids[], owasp_llm_ids[], verbatim_description, source_ref,
        exposure_check JSONB, mitigation JSONB, sector_amplifiers[],
        applies_to_jurisdictions[], version, last_updated)        -- global

raw_threat_feed(id, source, raw JSONB, ingested_at)               -- append-only, monthly partitions

threat_exposures(id, tenant_id, threat_id, status, evidence_refs[],
                 reasons, last_evaluated_at)                      -- RLS, unique (tenant_id, threat_id)

mitigation_actions(id, tenant_id, threat_id, integration_id, primitive,
                   params JSONB, status, proposed_by, approved_by,
                   applied_at, verified_at, rolled_back_at,
                   idempotency_key)                               -- RLS, append-only

endpoint_agent_events(id, tenant_id, device_id, kind, payload JSONB,
                      occurred_at)                                -- Timescale hypertable, monthly partitions

endpoint_devices(id, tenant_id, hostname, os, agent_version,
                 last_heartbeat, enrollment_token_hash)           -- RLS

modules_entitled(tenant_id, module_sku, valid_from, valid_to,
                 feature_flags JSONB)                             -- read on every gated request
```

---

## 6 · API surface added in Phase 7

```
GET  /v1/threats                              — catalogue, filter
GET  /v1/threats/{threat_id}                  — record + current exposure
POST /v1/threats/feed/refresh                 — admin trigger ingest
GET  /v1/threats/feed/pending-review          — admin queue
POST /v1/threats/{id}/publish                 — admin approve draft → published

GET  /v1/exposures                            — current tenant exposures
POST /v1/exposures/recompute                  — admin force re-run
GET  /v1/exposures/{threat_id}                — detail w/ predicate verdicts

GET  /v1/mitigations/proposed                 — queue
POST /v1/mitigations/{id}/approve
POST /v1/mitigations/{id}/reject
GET  /v1/mitigations                          — history

POST /v1/endpoint-agent/enroll                — device claims signed token
POST /v1/ingest/endpoint-agent                — OCSF events from EA

GET  /v1/licence                              — entitlements (admin)
```

Every gated route returns `402 Payment Required` with structured
`{module, action, contact}` when the calling tenant's licence does not
include the module — never a silent 404.

---

## 7 · Open items at start of Phase 7.1

1. IT-ISAC corporate-membership tier confirmation (commercial — non-blocking).
2. Module SKU pricing matrix (SCLLP commercial — non-blocking; structure shipped).
3. EULA / Master Agreement template (SCLLP-provided — required before licence-file issuance in 7.1).
4. Privacy counsel review of EA telemetry collection (must complete before 7.6).
5. AWS KMS asymmetric Ed25519 key — provisioning ticket raised at start of 7.1.

---

## 8 · This commit (scaffold-only)

What this PR ships on `phase-7/threat-intel`:

- `docs/PHASE-7-PLAN.md` — this document.
- `catalogue/threats/schema.yaml` — JSON-Schema for threat records.
- `catalogue/scripts/threats_validate.py` — schema + duplicate-ID validator.
- `catalogue/scripts/threats_digest.py` — SHA-256 inventory digest.
- `catalogue/threats/<source>/*.yaml` — 11 seed threats spanning OWASP
  LLM Top 10, POSIX (T7.x), MITRE ATLAS, and three sector packs.
- `catalogue/threats/.inventory_digest` — pinned digest of the seed catalogue.

No backend, no UI, no licence-enforcement code — those start in Phase 7.1
proper. This PR exists so the catalogue contract is reviewable and the
determinism digest baseline is locked before any engine code is written.
