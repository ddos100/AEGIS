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

from app.core.deps import CurrentUser, DBSession, require_analyst
from app.core.licence import requires_module
from app.models.mitigation_action import MitigationAction
from app.models.threat import Threat
from app.schemas.mitigations import (
    MitigationBrief,
    MitigationDecisionRequest,
    MitigationDetail,
    MitigationListResponse,
)


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
