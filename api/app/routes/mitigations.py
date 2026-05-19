"""Mitigation-action endpoints (Phase 7.4 — propose-only).

Gated by `requires_module("AEGIS-THREAT")` — mitigation orchestration
ships inside the same SKU as the catalogue + exposure engine.

What's implemented today:
  - GET    /v1/mitigations                  list (paginated, filterable)
  - GET    /v1/mitigations/{id}             single record detail
  - POST   /v1/mitigations/{id}/approve     analyst+ — moves to 'queued'
  - POST   /v1/mitigations/{id}/reject      analyst+ — moves to 'rejected'
  - POST   /v1/mitigations/{id}/dismiss     analyst+ — moves to 'dismissed'

Approving a mitigation does NOT push to a vendor API in this phase —
it transitions the row to `queued` and stamps approved_by/at. Phase 7.5
adds the per-integration adapters that drain the queue and write the
applied/verified/drifted lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst
from app.core.licence import requires_module
from app.core.crypto import decrypt_credentials
from app.integrations.mitigations import get_adapter, list_adapters
from app.models.integration_credential import IntegrationCredential
from app.models.mitigation_action import MitigationAction
from app.models.threat import Threat
from app.schemas.mitigations import (
    MitigationBrief,
    MitigationDecisionRequest,
    MitigationDetail,
    MitigationListResponse,
)
from app.services.verification_cadence import next_due


router = APIRouter(
    prefix="/mitigations",
    tags=["mitigations"],
    dependencies=[Depends(requires_module("AEGIS-THREAT"))],
)


# Sort order: queued first (ready to be applied), then proposed
# (needs decision), then everything else by status.
def _safe_uuid(value: str | UUID | None) -> UUID | None:
    """Best-effort UUID coercion; AuthenticatedUser.sub may carry a
    non-UUID synthetic value in edge cases (see app.core.auth)."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


_STATUS_RANK = {
    "queued":     0,
    "proposed":   1,
    "applied":    2,
    "verified":   3,
    "drifted":    4,
    "failed":     5,
    "rejected":   6,
    "dismissed":  7,
    "rolled_back": 8,
}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _to_brief(row: MitigationAction, threat: Threat) -> MitigationBrief:
    return MitigationBrief(
        id=row.id, tenant_id=row.tenant_id, threat_id=row.threat_id,
        exposure_id=row.exposure_id,
        integration=row.integration, action=row.action,
        preference=row.preference,
        requires_module=row.requires_module, severity_min=row.severity_min,
        status=row.status, status_reason=row.status_reason,
        proposed_at=row.proposed_at,
        approved_at=row.approved_at, applied_at=row.applied_at,
        verified_at=row.verified_at, rolled_back_at=row.rolled_back_at,
        threat_external_id=threat.threat_id, threat_title=threat.title,
        threat_severity=threat.severity,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@router.get("", response_model=MitigationListResponse)
async def list_mitigations(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    integration: Annotated[list[str] | None, Query()] = None,
) -> MitigationListResponse:
    stmt = (
        select(MitigationAction, Threat)
        .join(Threat, MitigationAction.threat_id == Threat.id)
    )
    if status_:
        stmt = stmt.where(MitigationAction.status.in_(status_))
    if severity:
        stmt = stmt.where(Threat.severity.in_(severity))
    if integration:
        stmt = stmt.where(MitigationAction.integration.in_(integration))

    pairs = (await db.execute(stmt)).all()
    pairs.sort(
        key=lambda r: (
            _STATUS_RANK.get(r[0].status, 99),
            _SEVERITY_RANK.get(r[1].severity, 99),
            r[1].threat_id,
        )
    )

    by_status: dict[str, int] = {}
    items: list[MitigationBrief] = []
    for row, threat in pairs:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        items.append(_to_brief(row, threat))
    return MitigationListResponse(items=items, by_status=by_status, total=len(items))


@router.get("/{mitigation_id}", response_model=MitigationDetail)
async def get_mitigation(
    mitigation_id: UUID,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> MitigationDetail:
    row = (await db.execute(
        select(MitigationAction).where(MitigationAction.id == mitigation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mitigation not found")
    threat = (await db.execute(
        select(Threat).where(Threat.id == row.threat_id)
    )).scalar_one_or_none()
    if threat is None:
        # FK constraint guards against this; surface as 500 if it happens.
        raise HTTPException(status_code=500, detail="Referenced threat missing")
    brief = _to_brief(row, threat)
    return MitigationDetail(
        **brief.model_dump(),
        params=row.params or {},
        idempotency_key=row.idempotency_key,
        last_error=row.last_error,
        threat_source_ref=threat.source_ref,
        vendor_ref=row.vendor_ref,
        state_blob=row.state_blob or {},
        verification_due_at=row.verification_due_at,
    )


# ---------------------------------------------------------------------------
# Decisions (approve / reject / dismiss)
# ---------------------------------------------------------------------------

async def _transition(
    db,
    mitigation_id: UUID,
    user_id: UUID,
    next_status: str,
    allowed_from: set[str],
    reason: str | None,
) -> MitigationAction:
    row = (await db.execute(
        select(MitigationAction).where(MitigationAction.id == mitigation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mitigation not found")
    if row.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from status={row.status!r} to {next_status!r}",
        )
    now = datetime.now(timezone.utc)
    row.status = next_status
    row.status_reason = reason
    if next_status == "queued":
        row.approved_at = now
        row.approved_by = user_id
    return row


@router.post("/{mitigation_id}/approve", response_model=MitigationDetail)
async def approve_mitigation(
    mitigation_id: UUID,
    payload: MitigationDecisionRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> MitigationDetail:
    user_uuid = _safe_uuid(user.sub)
    row = await _transition(
        db, mitigation_id, user_uuid,
        next_status="queued",
        allowed_from={"proposed"},
        reason=payload.reason,
    )
    return await get_mitigation(row.id, db, user)


@router.post("/{mitigation_id}/reject", response_model=MitigationDetail)
async def reject_mitigation(
    mitigation_id: UUID,
    payload: MitigationDecisionRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> MitigationDetail:
    user_uuid = _safe_uuid(user.sub)
    row = await _transition(
        db, mitigation_id, user_uuid,
        next_status="rejected",
        allowed_from={"proposed", "queued"},
        reason=payload.reason,
    )
    return await get_mitigation(row.id, db, user)


@router.post("/{mitigation_id}/dismiss", response_model=MitigationDetail)
async def dismiss_mitigation(
    mitigation_id: UUID,
    payload: MitigationDecisionRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> MitigationDetail:
    user_uuid = _safe_uuid(user.sub)
    row = await _transition(
        db, mitigation_id, user_uuid,
        next_status="dismissed",
        allowed_from={"proposed"},
        reason=payload.reason,
    )
    return await get_mitigation(row.id, db, user)


# ---------------------------------------------------------------------------
# Phase 7.5 — push / verify / rollback
# ---------------------------------------------------------------------------

@router.get("/_/adapters")
async def list_adapters_route(user: CurrentUser):  # noqa: ARG001
    """Inventory of every registered adapter. Used by the UI to know
    which (integration, action) pairs are wired (dry-run vs real)."""
    from app.schemas.mitigations import AdapterInfo
    return [AdapterInfo(**a) for a in list_adapters()]


async def _load_credentials(db, tenant_id: UUID, integration: str) -> dict | None:
    """Look up the tenant's active integration credentials for a vendor.

    Returns None when no credential row exists — adapters in dry-run mode
    can still proceed without one; real-mode adapters must error out.
    """
    row = (await db.execute(
        select(IntegrationCredential)
        .where((IntegrationCredential.integration == integration) &
               (IntegrationCredential.status == "active"))
        .order_by(IntegrationCredential.created_at)
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    try:
        return decrypt_credentials(row.credentials_ciphertext)
    except Exception:  # noqa: BLE001
        # Decryption failure is operationally critical but must not leak
        # detail to the API. Logged centrally; surface a 500 to the caller.
        raise HTTPException(status_code=500, detail="Failed to decrypt integration credentials")


@router.post("/{mitigation_id}/push")
async def push_mitigation(
    mitigation_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Push the mitigation to the vendor via the registered adapter.

    State machine:
        queued → applied   on success
        queued → failed    on adapter error (rows in `failed` are NOT
                           terminal for replay purposes — admin can flip
                           back to `proposed` via /reject + /recompute)
    Real apply is gated by the adapter's `dry_run` class attribute. In v1
    every shipped adapter is dry-run=True; no vendor traffic is generated.
    """
    from app.schemas.mitigations import PushReceipt

    row = (await db.execute(
        select(MitigationAction).where(MitigationAction.id == mitigation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mitigation not found")
    if row.status != "queued":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot push from status={row.status!r}; must be 'queued'",
        )

    try:
        adapter = get_adapter(row.integration, row.action)
    except KeyError as exc:
        # Adapter not registered → row goes to failed with the reason.
        row.status = "failed"
        row.last_error = f"No adapter registered for ({row.integration}, {row.action})"
        row.status_reason = row.last_error
        await db.flush()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    creds = await _load_credentials(db, user.tenant_id, row.integration)
    result = await adapter.apply(credentials=creds, params=row.params or {})

    now = datetime.now(timezone.utc)
    if result.ok:
        threat_row = (await db.execute(
            select(Threat).where(Threat.id == row.threat_id)
        )).scalar_one()
        row.status = "applied"
        row.applied_at = now
        row.vendor_ref = result.vendor_ref
        row.state_blob = result.state_blob or {}
        row.verification_due_at = next_due(threat_row.severity)
        row.last_error = None
        row.status_reason = (
            f"DRY-RUN apply succeeded. " if result.dry_run else ""
        ) + (result.detail or "")
    else:
        row.status = "failed"
        row.last_error = result.error or "adapter reported failure"
        row.status_reason = result.detail or None

    await db.flush()
    await db.refresh(row)
    detail = await get_mitigation(row.id, db, user)
    return PushReceipt(
        ok=result.ok, dry_run=result.dry_run, vendor_ref=result.vendor_ref,
        detail=result.detail, error=result.error, mitigation=detail,
    )


@router.post("/{mitigation_id}/verify")
async def verify_mitigation(
    mitigation_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
):
    """Re-check that the mitigation is still in place at the vendor.

    State transitions:
        applied → verified    on verify().verified
        applied → drifted     on verify().drifted or verify().missing
        applied → applied     on transient error (last_error stamped)
    Re-schedules `verification_due_at` per the locked severity cadence
    (15m / 1h / 6h / 24h).
    """
    from app.schemas.mitigations import VerifyReceipt

    row = (await db.execute(
        select(MitigationAction).where(MitigationAction.id == mitigation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mitigation not found")
    if row.status not in {"applied", "verified", "drifted"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot verify from status={row.status!r}",
        )

    try:
        adapter = get_adapter(row.integration, row.action)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    creds = await _load_credentials(db, user.tenant_id, row.integration)
    result = await adapter.verify(
        credentials=creds, params=row.params or {}, state_blob=row.state_blob,
    )

    now = datetime.now(timezone.utc)
    threat_row = (await db.execute(
        select(Threat).where(Threat.id == row.threat_id)
    )).scalar_one()

    if result.verified and not result.drifted and not result.missing:
        row.status = "verified"
        row.verified_at = now
        row.last_error = None
    elif result.drifted or result.missing:
        row.status = "drifted"
        row.last_error = result.detail or "drift detected"
    elif result.error:
        row.last_error = result.error
        # Keep current status; do not mask the previously-good apply.
    row.verification_due_at = next_due(threat_row.severity)

    await db.flush()
    await db.refresh(row)
    detail = await get_mitigation(row.id, db, user)
    return VerifyReceipt(
        verified=result.verified, drifted=result.drifted, missing=result.missing,
        dry_run=result.dry_run, detail=result.detail, error=result.error,
        mitigation=detail,
    )


@router.post("/{mitigation_id}/rollback")
async def rollback_mitigation(
    mitigation_id: UUID,
    payload: MitigationDecisionRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Roll back an applied / verified / drifted mitigation.

    Final state: `rolled_back` (terminal). No further state transitions
    are allowed; a fresh `proposed` row is generated by the next
    exposure recompute cycle if the threat remains exposed.
    """
    from app.schemas.mitigations import PushReceipt

    row = (await db.execute(
        select(MitigationAction).where(MitigationAction.id == mitigation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mitigation not found")
    if row.status not in {"applied", "verified", "drifted", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot rollback from status={row.status!r}",
        )

    try:
        adapter = get_adapter(row.integration, row.action)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    creds = await _load_credentials(db, user.tenant_id, row.integration)
    result = await adapter.rollback(
        credentials=creds, params=row.params or {}, state_blob=row.state_blob,
    )

    now = datetime.now(timezone.utc)
    if result.ok:
        row.status = "rolled_back"
        row.rolled_back_at = now
        row.verification_due_at = None
        row.status_reason = (payload.reason + " · " if payload.reason else "") + (
            "DRY-RUN rollback succeeded. " if result.dry_run else ""
        ) + (result.detail or "")
    else:
        row.last_error = result.error or "rollback failed"
        row.status_reason = (payload.reason + " · " if payload.reason else "") + (
            result.detail or ""
        )

    await db.flush()
    await db.refresh(row)
    detail = await get_mitigation(row.id, db, user)
    return PushReceipt(
        ok=result.ok, dry_run=result.dry_run, vendor_ref=result.vendor_ref,
        detail=result.detail, error=result.error, mitigation=detail,
    )


# ---------------------------------------------------------------------------
# Bulk decisions (Phase 7.6+ UX)
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Literal as _Literal


class _BulkMitigationDecision(BaseModel):
    ids:      list[UUID] = Field(..., min_length=1, max_length=200)
    decision: _Literal["approve", "reject", "dismiss"]
    reason:   str | None = Field(default=None, max_length=1000)


class _BulkMitigationResult(BaseModel):
    affected:    int
    skipped:     int = 0
    conflicts:   list[str] = Field(default_factory=list)


@router.post("/_/bulk-decide", response_model=_BulkMitigationResult)
async def bulk_decide_mitigations(
    payload: _BulkMitigationDecision,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
):
    """Apply approve / reject / dismiss to many proposals in one
    transaction. Per-row state-machine guards still apply: rows in a
    terminal state are skipped (counted in `conflicts`) rather than
    failing the whole batch."""
    user_uuid = _safe_uuid(user.sub)
    # Map decision to (next_status, allowed_from) — same rules as the
    # single-row endpoints.
    rules = {
        "approve": ("queued",    {"proposed"}),
        "reject":  ("rejected",  {"proposed", "queued"}),
        "dismiss": ("dismissed", {"proposed"}),
    }
    next_status, allowed_from = rules[payload.decision]
    rows = (await db.execute(
        select(MitigationAction).where(MitigationAction.id.in_(payload.ids))
    )).scalars().all()

    affected = 0
    conflicts: list[str] = []
    now = datetime.now(timezone.utc)
    for r in rows:
        if r.status not in allowed_from:
            conflicts.append(f"{r.id}:{r.status}")
            continue
        r.status = next_status
        r.status_reason = payload.reason
        if next_status == "queued":
            r.approved_at = now
            r.approved_by = user_uuid
        affected += 1
    skipped = len(payload.ids) - len(rows)
    await db.flush()
    return _BulkMitigationResult(
        affected=affected, skipped=skipped + len(conflicts),
        conflicts=conflicts,
    )
