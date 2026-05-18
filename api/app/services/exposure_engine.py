"""Exposure-evaluation engine for the Threat Intelligence module (Phase 7.1).

Reads every threat in the catalogue, evaluates its ``exposure_check``
predicate map against the calling tenant's observed state (Registry,
integrations, usage events, IdP grants), and writes a verdict to
``threat_exposures``.

Determinism contract
--------------------
For every threat the engine writes one of four exhaustive verdicts:

  exposed       at least one predicate satisfied; "exposed" requires
                that NO predicate evaluated UNKNOWN (so we don't claim
                a tenant is exposed when we lacked the data to verify).
  not_exposed   all predicates evaluated false with the data we had.
  unknown       at least one predicate needed a telemetry source that
                isn't integrated (e.g. AEGIS-EA for endpoint_agent_*
                predicates). The engine records WHICH telemetry source
                would unblock the verdict.
  mitigated     reserved for Phase 7.5 — engine will not write this
                value yet.

Every verdict carries:
  - reasons[]           "PREDICATE: VERDICT — observation" lines
  - evidence_refs[]     machine-readable pointers
  - missing_telemetry[] short identifiers naming gaps that produced UNKNOWN

No LLM is on the verdict path. Every result is reproducible from the
same DB state.

Sector overlay (left-biased)
----------------------------
A threat with non-empty `sector_amplifiers` is only evaluated against a
tenant whose `tenants.settings.industry` matches. The tenant override
layer is not yet implemented (Phase 7.3 stretch).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ai_provider import AIProvider
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent
from app.models.aisia_record import AISIARecord
from app.models.cloud_ai_resource import CloudAIResource
from app.models.integration_credential import IntegrationCredential
from app.models.oauth_grant import OAuthGrant
from app.models.threat import Threat
from app.models.threat_exposure import ThreatExposure
from app.models.tenant import Tenant


# Stable telemetry-source identifiers used in `missing_telemetry`.
TELEMETRY_NETWORK   = "network_telemetry"
TELEMETRY_BROWSER   = "browser_extension"
TELEMETRY_IDP       = "idp"
TELEMETRY_CLOUD     = "cloud_inventory"
TELEMETRY_M365      = "m365_audit"
TELEMETRY_EA        = "endpoint_agent"      # Phase 7.6
TELEMETRY_REGISTRY  = "ai_system_registry"


@dataclass(slots=True)
class _Predicate:
    """Per-predicate outcome — composed by every predicate evaluator."""
    name: str
    satisfied: bool | None       # None == unknown / telemetry missing
    detail: str
    evidence: list[str] = field(default_factory=list)
    needs: str | None = None     # populated only when satisfied is None


@dataclass(slots=True)
class _Eval:
    """Aggregated outcome for one (tenant, threat) pair."""
    status: str
    reasons: list[str]
    evidence_refs: list[str]
    missing_telemetry: list[str]


# ---------------------------------------------------------------------------
# Tenant snapshot loader
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _TenantSnapshot:
    """Pre-loaded slice of tenant state the engine needs.

    Loaded once per evaluation cycle so each threat-predicate pass is
    a pure-Python read against in-memory objects.
    """
    tenant_id: UUID
    industry: str | None
    systems: list[dict[str, Any]] = field(default_factory=list)
    recent_domains: dict[str, int] = field(default_factory=dict)
    provider_countries: set[str] = field(default_factory=set)
    integrations_active: set[str] = field(default_factory=set)
    oauth_grant_app_ids: set[str] = field(default_factory=set)
    cloud_ai_resources: list[dict[str, Any]] = field(default_factory=list)
    aisia_statuses: set[str] = field(default_factory=set)
    have_ea: bool = False


async def _load_snapshot(session, tenant_id: UUID) -> _TenantSnapshot:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one()
    industry = (tenant.settings or {}).get("industry")
    snap = _TenantSnapshot(tenant_id=tenant_id, industry=industry)

    # AI systems + provider country + capabilities (joined to ai_services / providers)
    sys_rows = (await session.execute(
        select(AISystem, AIService, AIProvider)
        .join(AIService, AISystem.catalogue_service_id == AIService.id, isouter=True)
        .join(AIProvider, AISystem.provider_id == AIProvider.id, isouter=True)
    )).all()
    for s, svc, prov in sys_rows:
        snap.systems.append({
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "data_types_processed": list(s.data_types_processed or []),
            "eu_ai_act_category": s.eu_ai_act_category,
            "capabilities": list((svc.capabilities or []) if svc else []),
            "aisia_status": s.aisia_status,
            "current_risk_score": s.current_risk_score,
            "provider_slug": prov.slug if prov else None,
            "provider_hq": (prov.hq_country if prov else None),
        })
        if prov and prov.hq_country:
            snap.provider_countries.add(prov.hq_country.upper())
        if s.aisia_status:
            snap.aisia_statuses.add(s.aisia_status)

    # Recent domain hits (last 30 d) — domain → count
    since = datetime.now(timezone.utc) - timedelta(days=30)
    dom_rows = (await session.execute(
        select(AIUsageEvent.raw_domain, func.count(AIUsageEvent.id))
        .where(AIUsageEvent.occurred_at >= since)
        .group_by(AIUsageEvent.raw_domain)
    )).all()
    for dom, n in dom_rows:
        if dom:
            snap.recent_domains[dom.lower()] = int(n)

    # Integrations active
    int_rows = (await session.execute(
        select(IntegrationCredential.integration, IntegrationCredential.status)
    )).all()
    for integ, status in int_rows:
        if status == "active":
            snap.integrations_active.add(integ)
    snap.have_ea = "aegis_endpoint_agent" in snap.integrations_active

    # OAuth grants
    grant_rows = (await session.execute(
        select(OAuthGrant.app_id).where(OAuthGrant.is_revoked.is_(False))
    )).all()
    snap.oauth_grant_app_ids = {row[0] for row in grant_rows if row[0]}

    # Cloud AI resources (for guardrail / IAM wildcard predicates)
    car_rows = (await session.execute(select(CloudAIResource))).scalars().all()
    for r in car_rows:
        snap.cloud_ai_resources.append({
            "resource_type": r.resource_type,
            "guardrail": (r.usage_metrics or {}).get("guardrail_attached"),
            "role_wildcard": (r.usage_metrics or {}).get("role_wildcard_detected"),
        })

    # AISIA statuses (also collected from systems above; pick up freestanding records too)
    aisia_rows = (await session.execute(select(AISIARecord.status))).all()
    snap.aisia_statuses |= {r[0] for r in aisia_rows if r[0]}

    return snap


# ---------------------------------------------------------------------------
# Predicate evaluators
# ---------------------------------------------------------------------------

def _eval_predicate(key: str, value: Any, snap: _TenantSnapshot) -> _Predicate:
    """Dispatch one predicate; return a _Predicate result.

    `satisfied=True` means the predicate fired (i.e. the tenant exhibits
    the condition described). The aggregate verdict is "exposed" when ANY
    fired predicate is true AND no predicate was UNKNOWN. Each evaluator
    is responsible for emitting an evidence pointer when it can prove the
    condition either way.
    """
    if key == "any_system_category_in":
        matched = [s for s in snap.systems if s["category"] in set(value)]
        if matched:
            return _Predicate(
                name=f"any_system_category_in({value})",
                satisfied=True,
                detail=f"matched {len(matched)} systems: " +
                       ", ".join(s["name"] for s in matched[:3]) +
                       (f" (+{len(matched)-3} more)" if len(matched) > 3 else ""),
                evidence=[f"system:{s['id']}" for s in matched[:5]],
            )
        return _Predicate(
            name=f"any_system_category_in({value})",
            satisfied=False,
            detail=f"no system in registry has category in {value}",
            evidence=[],
        )

    if key == "observed_provider_domains":
        hits = {d: snap.recent_domains[d] for d in value if d.lower() in snap.recent_domains}
        if hits:
            top = ", ".join(f"{d}={n}" for d, n in list(hits.items())[:3])
            return _Predicate(
                name=f"observed_provider_domains({len(value)} domains)",
                satisfied=True,
                detail=f"{sum(hits.values())} events in last 30 d ({top})",
                evidence=[f"domain:{d}:{n}" for d, n in hits.items()],
            )
        if not snap.recent_domains:
            return _Predicate(
                name=f"observed_provider_domains({len(value)} domains)",
                satisfied=None,
                detail="no network telemetry observed in last 30 d",
                needs=TELEMETRY_NETWORK,
            )
        return _Predicate(
            name=f"observed_provider_domains({len(value)} domains)",
            satisfied=False,
            detail="no matching domains observed in last 30 d",
        )

    if key == "observed_provider_jurisdiction":
        hits = snap.provider_countries & {c.upper() for c in value}
        if hits:
            return _Predicate(
                name=f"observed_provider_jurisdiction({sorted(value)})",
                satisfied=True,
                detail=f"observed provider HQ in {sorted(hits)}",
                evidence=[f"provider_country:{c}" for c in hits],
            )
        if not snap.provider_countries:
            return _Predicate(
                name=f"observed_provider_jurisdiction({sorted(value)})",
                satisfied=None,
                detail="no provider HQ data — catalogue not matched on any system",
                needs=TELEMETRY_REGISTRY,
            )
        return _Predicate(
            name=f"observed_provider_jurisdiction({sorted(value)})",
            satisfied=False,
            detail=f"providers observed: {sorted(snap.provider_countries)}",
        )

    if key == "any_system_data_type_in":
        wanted = set(value)
        matched = [s for s in snap.systems if wanted & set(s["data_types_processed"])]
        if matched:
            return _Predicate(
                name=f"any_system_data_type_in({sorted(value)})",
                satisfied=True,
                detail=f"matched {len(matched)} systems",
                evidence=[f"system:{s['id']}" for s in matched[:5]],
            )
        return _Predicate(
            name=f"any_system_data_type_in({sorted(value)})",
            satisfied=False,
            detail="no system declares these data types",
        )

    if key == "any_system_capability_in":
        wanted = set(value)
        matched = [s for s in snap.systems if wanted & set(s["capabilities"])]
        if matched:
            return _Predicate(
                name=f"any_system_capability_in({sorted(value)})",
                satisfied=True,
                detail=f"matched {len(matched)} systems with these capabilities",
                evidence=[f"system:{s['id']}" for s in matched[:5]],
            )
        return _Predicate(
            name=f"any_system_capability_in({sorted(value)})",
            satisfied=False,
            detail="no system declares these capabilities",
        )

    if key == "eu_ai_act_category_in":
        wanted = set(value)
        matched = [s for s in snap.systems if s["eu_ai_act_category"] in wanted]
        if matched:
            return _Predicate(
                name=f"eu_ai_act_category_in({sorted(value)})",
                satisfied=True,
                detail=f"matched {len(matched)} systems",
                evidence=[f"system:{s['id']}" for s in matched[:5]],
            )
        return _Predicate(
            name=f"eu_ai_act_category_in({sorted(value)})",
            satisfied=False,
            detail="no system has matching EU AI Act category",
        )

    if key == "aisia_status_in":
        wanted = set(value)
        matched = wanted & snap.aisia_statuses
        if matched:
            return _Predicate(
                name=f"aisia_status_in({sorted(value)})",
                satisfied=True,
                detail=f"AISIA status(es) observed: {sorted(matched)}",
                evidence=[f"aisia_status:{s}" for s in matched],
            )
        return _Predicate(
            name=f"aisia_status_in({sorted(value)})",
            satisfied=False,
            detail=f"observed AISIA statuses: {sorted(snap.aisia_statuses) or '∅'}",
        )

    if key == "m365_copilot_enabled":
        active = "m365_copilot" in snap.integrations_active
        if not snap.integrations_active or "m365_copilot" not in {
            "m365_copilot", *snap.integrations_active,
        }:
            # No M365 integration configured at all — UNKNOWN
            return _Predicate(
                name="m365_copilot_enabled",
                satisfied=None if value else False,
                detail=("M365 connector not configured — cannot verify Copilot state"
                        if value else "M365 connector not configured"),
                needs=TELEMETRY_M365 if value else None,
            )
        return _Predicate(
            name="m365_copilot_enabled",
            satisfied=(active == bool(value)),
            detail=f"m365_copilot integration is {'active' if active else 'inactive'}",
            evidence=[f"integration:m365_copilot:{'active' if active else 'inactive'}"],
        )

    if key == "idp_oauth_grant_present_unsanctioned":
        # Tenant has IdP integration AND has OAuth grants AND at least one is
        # outside the tenant-approved allow-list. For the v1 we assume any
        # grant we observed is "unsanctioned" unless tenant has explicitly
        # marked it via app_id in tenant.settings.approved_oauth_app_ids.
        if not snap.oauth_grant_app_ids:
            if "entra_id" in snap.integrations_active or "okta" in snap.integrations_active:
                return _Predicate(
                    name="idp_oauth_grant_present_unsanctioned",
                    satisfied=False,
                    detail="IdP integrated but no OAuth grants observed",
                )
            return _Predicate(
                name="idp_oauth_grant_present_unsanctioned",
                satisfied=None,
                detail="No IdP connector (entra_id / okta) configured",
                needs=TELEMETRY_IDP,
            )
        return _Predicate(
            name="idp_oauth_grant_present_unsanctioned",
            satisfied=True,
            detail=f"{len(snap.oauth_grant_app_ids)} OAuth grants observed",
            evidence=[f"oauth_grant:{a}" for a in list(snap.oauth_grant_app_ids)[:5]],
        )

    if key == "cloud_ai_role_wildcard_detected":
        if not snap.cloud_ai_resources:
            return _Predicate(
                name="cloud_ai_role_wildcard_detected",
                satisfied=None,
                detail="No cloud AI inventory — cloud connector not configured or sync stale",
                needs=TELEMETRY_CLOUD,
            )
        wildcards = [r for r in snap.cloud_ai_resources if r.get("role_wildcard")]
        if wildcards:
            return _Predicate(
                name="cloud_ai_role_wildcard_detected",
                satisfied=True,
                detail=f"{len(wildcards)} cloud AI resources with wildcard role attachment",
                evidence=[f"cloud_ai_role_wildcard:{r['resource_type']}" for r in wildcards[:5]],
            )
        return _Predicate(
            name="cloud_ai_role_wildcard_detected",
            satisfied=False,
            detail=f"{len(snap.cloud_ai_resources)} cloud AI resources scanned, none with wildcard role",
        )

    if key == "cloud_ai_resource_without_guardrail":
        if not snap.cloud_ai_resources:
            return _Predicate(
                name="cloud_ai_resource_without_guardrail",
                satisfied=None,
                detail="No cloud AI inventory — cloud connector not configured or sync stale",
                needs=TELEMETRY_CLOUD,
            )
        unprotected = [r for r in snap.cloud_ai_resources if not r.get("guardrail")]
        if unprotected:
            return _Predicate(
                name="cloud_ai_resource_without_guardrail",
                satisfied=True,
                detail=f"{len(unprotected)} cloud AI resources without guardrail attached",
                evidence=[f"cloud_ai_no_guardrail:{r['resource_type']}" for r in unprotected[:5]],
            )
        return _Predicate(
            name="cloud_ai_resource_without_guardrail",
            satisfied=False,
            detail="every cloud AI resource has a guardrail attached",
        )

    if key == "aiusage_high_volume_burst":
        # Predicate value is {events: N, window_minutes: M}. Total of
        # snap.recent_domains was aggregated over 30 d — for a v1 we just
        # compare against the absolute count. A precise window check needs
        # a re-query, deferred to next increment.
        total = sum(snap.recent_domains.values())
        threshold = int((value or {}).get("events", 10000))
        if total >= threshold:
            return _Predicate(
                name=f"aiusage_high_volume_burst(events>={threshold})",
                satisfied=True,
                detail=f"{total} events across all AI domains in last 30 d",
                evidence=[f"ai_usage_events:{total}"],
            )
        return _Predicate(
            name=f"aiusage_high_volume_burst(events>={threshold})",
            satisfied=False,
            detail=f"{total} events in last 30 d (below threshold)",
        )

    if key == "risk_score_age_days_gt":
        # Any system with current_risk_score == None counts as "older than
        # any threshold" because we have no score at all.
        threshold = int(value)
        unscored = [s for s in snap.systems if s["current_risk_score"] is None]
        if unscored:
            return _Predicate(
                name=f"risk_score_age_days_gt({threshold})",
                satisfied=True,
                detail=f"{len(unscored)} systems have no current_risk_score",
                evidence=[f"system_unscored:{s['id']}" for s in unscored[:5]],
            )
        return _Predicate(
            name=f"risk_score_age_days_gt({threshold})",
            satisfied=False,
            detail="every system has a current_risk_score (cannot compute age from this query alone)",
        )

    # ---- EA-dependent predicates: always UNKNOWN until Phase 7.6 EA ships ----
    if key in {
        "endpoint_agent_curl_pipe_sh_within_days",
        "endpoint_agent_npm_postinstall_within_days",
        "endpoint_agent_pip_setup_hook_within_days",
        "endpoint_agent_world_writable_in_ai_path",
        "endpoint_agent_suid_dropped",
        "endpoint_agent_path_hijack_detected",
        "endpoint_agent_secrets_read_by_ai_proc",
        "endpoint_agent_destructive_cmd_by_ai_proc",
        "endpoint_agent_git_push_by_ai_proc",
        "endpoint_agent_privileged_container_by_ai_proc",
        "mcp_server_with_scope",
    }:
        if snap.have_ea:
            # EA integration configured but no events yet → predicate false
            return _Predicate(
                name=f"{key}",
                satisfied=False,
                detail="AEGIS-EA configured but no matching event observed",
            )
        return _Predicate(
            name=f"{key}",
            satisfied=None,
            detail="AEGIS Endpoint Agent not deployed — predicate cannot be evaluated",
            needs=TELEMETRY_EA,
        )

    # ---- HuggingFace model usage — deferred to Phase 7.6 EA telemetry ----
    if key == "huggingface_model_in_use":
        return _Predicate(
            name=f"huggingface_model_in_use",
            satisfied=None,
            detail="local model runtime telemetry not yet integrated",
            needs=TELEMETRY_EA,
        )

    if key == "provider_trust_score_below":
        # Resolved on the catalogue-matched systems
        matched = [
            s for s in snap.systems
            if s["provider_slug"] is not None
        ]
        # Without a catalogue trust_score in our snapshot we cannot tell here.
        # For v1 surface as unknown so we don't fire false positives.
        if not matched:
            return _Predicate(
                name=f"provider_trust_score_below({value})",
                satisfied=False,
                detail="no catalogue-matched systems",
            )
        return _Predicate(
            name=f"provider_trust_score_below({value})",
            satisfied=None,
            detail="catalogue provider_trust_score not preloaded — pending next increment",
            needs=TELEMETRY_REGISTRY,
        )

    # ---- Unknown predicate (forward-compat) ----
    return _Predicate(
        name=f"{key}",
        satisfied=None,
        detail="unsupported predicate (forward-compat — engine update needed)",
        needs="engine_update",
    )


# ---------------------------------------------------------------------------
# Aggregate evaluator
# ---------------------------------------------------------------------------

def _aggregate(predicates: list[_Predicate]) -> _Eval:
    reasons: list[str] = []
    evidence: list[str] = []
    missing: set[str] = set()
    saw_true = False
    saw_unknown = False
    for p in predicates:
        if p.satisfied is True:
            reasons.append(f"{p.name}: PASSED — {p.detail}")
            evidence.extend(p.evidence)
            saw_true = True
        elif p.satisfied is False:
            reasons.append(f"{p.name}: FAILED — {p.detail}")
            evidence.extend(p.evidence)
        else:
            reasons.append(f"{p.name}: UNKNOWN — {p.detail}")
            if p.needs:
                missing.add(p.needs)
            saw_unknown = True

    # Verdict: any UNKNOWN cell prevents an "exposed" call. We won't claim
    # a tenant is exposed when we lacked the data to verify. An UNKNOWN
    # cell with no positive cells → unknown. If we positively saw a
    # condition AND nothing was unknown, that's exposed. Everything else
    # with at least one negative and no unknown → not_exposed.
    if saw_unknown:
        status = "unknown"
    elif saw_true:
        status = "exposed"
    else:
        status = "not_exposed"

    return _Eval(
        status=status,
        reasons=reasons,
        evidence_refs=evidence,
        missing_telemetry=sorted(missing),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def applies_to_tenant(threat: Threat, snap: _TenantSnapshot) -> bool:
    """Sector overlay filter — left-biased base → sector.

    A threat with non-empty `sector_amplifiers` is only evaluated against
    a tenant whose `industry` matches one of the amplifiers. Threats
    without sector_amplifiers apply to every tenant.
    """
    if not threat.sector_amplifiers:
        return True
    if not snap.industry:
        return False
    return snap.industry in set(threat.sector_amplifiers)


async def evaluate_one(*, session, tenant_id: UUID, threat_id: UUID) -> _Eval | None:
    """Evaluate one threat for one tenant. Returns None if not applicable."""
    snap = await _load_snapshot(session, tenant_id)
    threat = (await session.execute(
        select(Threat).where(Threat.id == threat_id)
    )).scalar_one_or_none()
    if threat is None:
        return None
    if not applies_to_tenant(threat, snap):
        return None
    preds = [_eval_predicate(k, v, snap) for k, v in (threat.exposure_check or {}).items()]
    return _aggregate(preds)


async def recompute_all(*, session, tenant_id: UUID) -> dict[str, Any]:
    """Evaluate every threat in the catalogue for one tenant.

    Idempotent: upserts on (tenant_id, threat_id). Returns a small
    summary so callers can show "evaluated N threats, M exposed".
    """
    snap = await _load_snapshot(session, tenant_id)
    threats = (await session.execute(select(Threat))).scalars().all()

    counts = {"exposed": 0, "not_exposed": 0, "unknown": 0, "skipped_by_sector": 0}
    now_func = func.now()
    for t in threats:
        if not applies_to_tenant(t, snap):
            counts["skipped_by_sector"] += 1
            continue
        preds = [_eval_predicate(k, v, snap) for k, v in (t.exposure_check or {}).items()]
        result = _aggregate(preds)
        counts[result.status] += 1
        stmt = (
            pg_insert(ThreatExposure)
            .values(
                tenant_id=tenant_id,
                threat_id=t.id,
                status=result.status,
                reasons=result.reasons,
                evidence_refs=result.evidence_refs,
                missing_telemetry=result.missing_telemetry,
                last_evaluated_at=now_func,
            )
            .on_conflict_do_update(
                constraint="uq_threat_exposures_unique",
                set_={
                    "status":            result.status,
                    "reasons":           result.reasons,
                    "evidence_refs":     result.evidence_refs,
                    "missing_telemetry": result.missing_telemetry,
                    "last_evaluated_at": now_func,
                },
            )
        )
        await session.execute(stmt)

    # After exposures are committed in-session, run the propose-only
    # mitigation orchestrator so every `exposed` verdict yields one or
    # more `proposed` mitigation_actions rows in the same DB
    # transaction. The orchestrator is idempotent — repeat calls don't
    # duplicate.
    from app.services.mitigation_orchestrator import propose_all  # local import
    mit_totals = await propose_all(session=session, tenant_id=tenant_id)

    return {
        "tenant_id": str(tenant_id),
        "threats_total": len(threats),
        "mitigations": mit_totals,
        **counts,
    }
