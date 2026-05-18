"""Threat exposure endpoints (Phase 7.1 increment).

Routes are gated by `requires_module("AEGIS-THREAT")` — same SKU as the
catalogue routes since exposure analysis is the core deliverable of that
module.

Mitigation orchestration (Phase 7.4) and the exposure WebSocket feed
(Phase 7.5) attach to this router in later increments.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession, require_analyst
from app.core.licence import requires_module
from app.models.threat import Threat
from app.models.threat_exposure import ThreatExposure
from app.schemas.exposures import (
    ExposureBrief,
    ExposureDetail,
    ExposureListResponse,
    RecomputeResponse,
)
from app.services.exposure_engine import recompute_all

router = APIRouter(
    prefix="/exposures",
    tags=["exposures"],
    dependencies=[Depends(requires_module("AEGIS-THREAT"))],
)


@router.get("", response_model=ExposureListResponse)
async def list_exposures(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    severity: Annotated[list[str] | None, Query()] = None,
) -> ExposureListResponse:
    stmt = (
        select(ThreatExposure, Threat)
        .join(Threat, ThreatExposure.threat_id == Threat.id)
    )
    if status_:
        stmt = stmt.where(ThreatExposure.status.in_(status_))
    if severity:
        stmt = stmt.where(Threat.severity.in_(severity))

    # Deterministic ordering: exposed first (highest concern), then
    # unknown (next action), then not_exposed, then by severity.
    sort_status = {
        "exposed": 0, "unknown": 1, "not_exposed": 2, "mitigated": 3,
    }
    sort_severity = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    pairs = (await db.execute(stmt)).all()
    pairs.sort(
        key=lambda r: (
            sort_status.get(r[0].status, 99),
            sort_severity.get(r[1].severity, 99),
            r[1].threat_id,
        )
    )

    items: list[ExposureBrief] = []
    by_status: dict[str, int] = {"exposed": 0, "not_exposed": 0, "unknown": 0, "mitigated": 0}
    for exp, threat in pairs:
        by_status[exp.status] = by_status.get(exp.status, 0) + 1
        items.append(ExposureBrief(
            id=exp.id, tenant_id=exp.tenant_id, threat_id=exp.threat_id,
            status=exp.status, last_evaluated_at=exp.last_evaluated_at,
            threat_external_id=threat.threat_id,
            threat_title=threat.title,
            threat_severity=threat.severity,
            threat_classes=threat.classes,
            threat_vectors=threat.vectors,
        ))
    return ExposureListResponse(items=items, by_status=by_status, total=len(items))


@router.get("/{threat_external_id}", response_model=ExposureDetail)
async def get_exposure(
    threat_external_id: str,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> ExposureDetail:
    threat = (await db.execute(
        select(Threat).where(Threat.threat_id == threat_external_id)
    )).scalar_one_or_none()
    if threat is None:
        raise HTTPException(status_code=404, detail="Threat not found")
    exposure = (await db.execute(
        select(ThreatExposure).where(ThreatExposure.threat_id == threat.id)
    )).scalar_one_or_none()
    if exposure is None:
        raise HTTPException(
            status_code=404,
            detail="No exposure verdict yet for this threat. Run POST /v1/exposures/recompute."
        )
    return ExposureDetail(
        id=exposure.id, tenant_id=exposure.tenant_id, threat_id=exposure.threat_id,
        status=exposure.status, last_evaluated_at=exposure.last_evaluated_at,
        reasons=exposure.reasons, evidence_refs=exposure.evidence_refs,
        missing_telemetry=exposure.missing_telemetry,
        threat_external_id=threat.threat_id,
        threat_title=threat.title,
        threat_severity=threat.severity,
        threat_classes=threat.classes,
        threat_vectors=threat.vectors,
        threat_source_ref=threat.source_ref,
        threat_verbatim_description=threat.verbatim_description,
        threat_exposure_check=threat.exposure_check or {},
        threat_mitigation=threat.mitigation,
    )


@router.post("/recompute", response_model=RecomputeResponse)
async def recompute(
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> RecomputeResponse:
    result = await recompute_all(session=db, tenant_id=user.tenant_id)
    return RecomputeResponse(**result)
