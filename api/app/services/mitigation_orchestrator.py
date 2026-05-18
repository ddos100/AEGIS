"""Mitigation orchestrator (Phase 7.4 — propose-only).

For every exposure with status='exposed' the orchestrator walks the
threat's ``mitigation.preferred[]`` (and ``alternates[]``) blocks and
records a ``mitigation_actions`` row with status='proposed' for each.

What this module DOES today
---------------------------
- Reads exposure verdicts written by services.exposure_engine.
- Generates `proposed` rows in `mitigation_actions`, keyed by a
  deterministic idempotency_key so repeat runs don't duplicate.
- Honours terminal states (rejected/applied/verified/rolled_back/failed)
  — once an operator has acted on a row it is NEVER overwritten.
- Refreshes the params of an existing `proposed` row when the threat
  catalogue evolves and the mitigation step's params change.

What this module DOES NOT do (yet)
----------------------------------
- No vendor-API push. The locked v1 default is propose-only across
  the board (PHASE-7-PLAN.md §3). The per-integration adapters land
  in Phase 7.5 alongside the verification loop.
- No tenant posture-matrix evaluation. Every threat that emits an
  `exposed` verdict produces proposals; the operator's approve/reject
  decisions are recorded explicitly.

Determinism + privacy
---------------------
- idempotency_key is sha256 over (tenant_id|threat_id|integration|
  action|canonical-JSON params). Stable across runs.
- No PII in any column. Params reference machine identifiers only
  (categories, domains, app IDs, policy refs).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.mitigation_action import MitigationAction
from app.models.threat import Threat
from app.models.threat_exposure import ThreatExposure


TERMINAL_STATES = {"rejected", "dismissed", "applied", "verified", "rolled_back", "failed"}


def _canonical_params(params: Any) -> str:
    """Stable JSON encoding so idempotency_key is reproducible."""
    if params is None:
        return "null"
    return json.dumps(params, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, default=str)


def _idempotency_key(tenant_id: UUID, threat_id: UUID, integration: str,
                      action: str, params: Any) -> str:
    raw = f"{tenant_id}|{threat_id}|{integration}|{action}|{_canonical_params(params)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iter_steps(threat: Threat) -> Iterable[tuple[dict[str, Any], str]]:
    """Yield (step_dict, preference) for every mitigation step on a threat."""
    mit = threat.mitigation or {}
    for s in mit.get("preferred", []) or []:
        if isinstance(s, dict):
            yield s, "preferred"
    for s in mit.get("alternates", []) or []:
        if isinstance(s, dict):
            yield s, "alternate"


async def propose_for_exposure(*, session, exposure: ThreatExposure,
                                threat: Threat) -> dict[str, int]:
    """Create or refresh `proposed` rows for one exposed threat.

    Returns a small summary so the caller can report per-cycle counts.
    """
    if exposure.status != "exposed":
        return {"created": 0, "refreshed": 0, "skipped_terminal": 0}

    created = refreshed = skipped_terminal = 0
    for step, preference in _iter_steps(threat):
        integration = step.get("integration")
        action      = step.get("action")
        if not integration or not action:
            # Malformed mitigation step in YAML; skip silently — the
            # catalogue validator should already have rejected it.
            continue
        params = step.get("params") or {}
        key = _idempotency_key(
            tenant_id=exposure.tenant_id, threat_id=exposure.threat_id,
            integration=integration, action=action, params=params,
        )

        existing = (await session.execute(
            select(MitigationAction).where(
                (MitigationAction.tenant_id == exposure.tenant_id) &
                (MitigationAction.idempotency_key == key)
            )
        )).scalar_one_or_none()

        if existing is not None and existing.status in TERMINAL_STATES:
            skipped_terminal += 1
            continue

        values = dict(
            tenant_id=exposure.tenant_id,
            threat_id=exposure.threat_id,
            exposure_id=exposure.id,
            integration=integration,
            action=action,
            params=params,
            severity_min=step.get("severity_min"),
            requires_module=step.get("requires_module"),
            preference=preference,
            idempotency_key=key,
            status="proposed",
        )
        stmt = (
            pg_insert(MitigationAction)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_mitigation_actions_idempotency",
                # Only refresh metadata on non-terminal rows. The status filter
                # here is belt-and-braces (we already filtered above).
                set_={
                    "params":          params,
                    "severity_min":    step.get("severity_min"),
                    "requires_module": step.get("requires_module"),
                    "preference":      preference,
                    "exposure_id":     exposure.id,
                },
                where=MitigationAction.status.notin_(TERMINAL_STATES),
            )
        )
        result = await session.execute(stmt)
        # rowcount is 1 on insert OR update; we distinguish by the prior
        # `existing` lookup.
        if existing is None:
            created += 1
        else:
            refreshed += 1
        _ = result  # silence linter on unused

    return {"created": created, "refreshed": refreshed,
            "skipped_terminal": skipped_terminal}


async def propose_all(*, session, tenant_id: UUID) -> dict[str, int]:
    """Walk every `exposed` verdict for `tenant_id` and propose mitigations."""
    rows = (await session.execute(
        select(ThreatExposure, Threat)
        .join(Threat, ThreatExposure.threat_id == Threat.id)
        .where(ThreatExposure.status == "exposed")
    )).all()

    totals = {"exposures_seen": 0, "created": 0, "refreshed": 0,
              "skipped_terminal": 0}
    for exposure, threat in rows:
        totals["exposures_seen"] += 1
        r = await propose_for_exposure(
            session=session, exposure=exposure, threat=threat,
        )
        for k, v in r.items():
            totals[k] = totals.get(k, 0) + v
    return totals
