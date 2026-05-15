"""Compliance endpoints (Phase 5)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst
from app.models.compliance_control import ComplianceControl
from app.models.compliance_framework import ComplianceFramework
from app.models.compliance_mapping import ComplianceMapping
from app.schemas.compliance import (
    AutoAssessResult,
    ControlBrief,
    FrameworkBrief,
    FrameworkScoreResp,
    MappingDetail,
    MappingUpdate,
)
from app.services.compliance_engine import auto_assess, framework_score

router = APIRouter(prefix="/compliance", tags=["compliance"])


# ---------- frameworks ----------

@router.get("/frameworks", response_model=list[FrameworkBrief])
async def list_frameworks(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(
        select(ComplianceFramework).order_by(ComplianceFramework.name)
    )).scalars().all()
    return [FrameworkBrief.model_validate(r) for r in rows]


@router.get("/frameworks/{slug}", response_model=FrameworkBrief)
async def get_framework(slug: str, db: DBSession, user: CurrentUser) -> FrameworkBrief:  # noqa: ARG001
    row = (await db.execute(
        select(ComplianceFramework).where(ComplianceFramework.slug == slug)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    return FrameworkBrief.model_validate(row)


@router.get("/frameworks/{slug}/controls", response_model=list[ControlBrief])
async def list_controls(slug: str, db: DBSession, user: CurrentUser):  # noqa: ARG001
    framework = (await db.execute(
        select(ComplianceFramework).where(ComplianceFramework.slug == slug)
    )).scalar_one_or_none()
    if framework is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    rows = (await db.execute(
        select(ComplianceControl)
        .where(ComplianceControl.framework_id == framework.id)
        .order_by(ComplianceControl.control_id)
    )).scalars().all()
    return [ControlBrief.model_validate(r) for r in rows]


@router.get("/frameworks/{slug}/score", response_model=FrameworkScoreResp)
async def get_framework_score(slug: str, db: DBSession, user: CurrentUser):  # noqa: ARG001
    score = await framework_score(session=db, framework_slug=slug)
    if score is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    return FrameworkScoreResp(
        framework_id=score.framework_id, slug=score.slug, name=score.name,
        total_controls=score.total_controls, by_status=score.by_status,
        score_pct=score.score_pct, gaps=score.gaps,
    )


@router.post("/frameworks/{slug}/auto-assess", response_model=AutoAssessResult,
             status_code=status.HTTP_202_ACCEPTED)
async def trigger_auto_assess(
    slug: str,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> AutoAssessResult:
    """Run the compliance engine across every AISystem for this framework."""
    result = await auto_assess(session=db, tenant_id=user.tenant_id, framework_slug=slug)
    return AutoAssessResult(**result)


# ---------- mappings ----------

@router.get("/frameworks/{slug}/mappings", response_model=list[MappingDetail])
async def list_framework_mappings(
    slug: str,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> list[MappingDetail]:
    """Every mapping for one framework, in deterministic order.

    Sorted by `(control_id, ai_system_id)` so the UI's reason / evidence
    output for the same compliance state is byte-stable across reloads.
    """
    fid = (await db.execute(
        select(ComplianceFramework.id).where(ComplianceFramework.slug == slug)
    )).scalar_one_or_none()
    if fid is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    rows = (await db.execute(
        select(ComplianceMapping)
        .join(ComplianceControl, ComplianceMapping.control_id == ComplianceControl.id)
        .where(ComplianceControl.framework_id == fid)
        .order_by(ComplianceControl.control_id, ComplianceMapping.ai_system_id)
    )).scalars().all()
    return [MappingDetail.model_validate(r) for r in rows]


@router.get("/mappings", response_model=list[MappingDetail])
async def list_mappings(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    framework_slug: str | None = None,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = select(ComplianceMapping).limit(limit)
    if framework_slug:
        fid = (await db.execute(
            select(ComplianceFramework.id).where(ComplianceFramework.slug == framework_slug)
        )).scalar_one_or_none()
        if fid:
            stmt = stmt.join(ComplianceControl,
                             ComplianceMapping.control_id == ComplianceControl.id) \
                       .where(ComplianceControl.framework_id == fid)
    if status_:
        stmt = stmt.where(ComplianceMapping.status.in_(status_))
    rows = (await db.execute(stmt)).scalars().all()
    return [MappingDetail.model_validate(r) for r in rows]


@router.patch("/mappings/{mapping_id}", response_model=MappingDetail)
async def update_mapping(
    mapping_id: UUID,
    payload: MappingUpdate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> MappingDetail:
    row = (await db.execute(
        select(ComplianceMapping).where(ComplianceMapping.id == mapping_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return MappingDetail.model_validate(row)
