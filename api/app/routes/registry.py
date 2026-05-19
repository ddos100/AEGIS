"""AI System Registry — tenant-scoped CRUD + stats + from-catalogue quick-add."""
from __future__ import annotations

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from app.core.deps import CurrentUser, DBSession, require_analyst
from fastapi import Depends
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.schemas.common import Page
from app.schemas.registry import (
    AISystemCreate,
    AISystemDetail,
    AISystemListItem,
    AISystemUpdate,
    FromCatalogueRequest,
    RegistryStats,
)

router = APIRouter(prefix="/registry", tags=["registry"])


# ---------- list ----------

@router.get("/systems", response_model=Page[AISystemListItem])
async def list_systems(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 25,
    q: str | None = None,
    category: Annotated[list[str] | None, Query()] = None,
    risk_level: Annotated[list[str] | None, Query()] = None,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    is_shadow: bool | None = None,
    department_id: UUID | None = None,
    sort: str = Query("created_at_desc", description="Sort key"),
) -> Page[AISystemListItem]:
    stmt = select(AISystem)

    if category:
        stmt = stmt.where(AISystem.category.in_(category))
    if risk_level:
        stmt = stmt.where(AISystem.risk_level.in_(risk_level))
    if status_:
        stmt = stmt.where(AISystem.status.in_(status_))
    if is_shadow is not None:
        stmt = stmt.where(AISystem.is_shadow.is_(is_shadow))
    if department_id:
        stmt = stmt.where(AISystem.department_id == department_id)
    if q:
        pat = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AISystem.name).like(pat),
                func.lower(AISystem.internal_alias).like(pat),
                func.lower(AISystem.intended_purpose).like(pat),
            )
        )

    sort_clauses = {
        "created_at_desc": AISystem.created_at.desc(),
        "created_at_asc":  AISystem.created_at.asc(),
        "name_asc":        AISystem.name.asc(),
        "name_desc":       AISystem.name.desc(),
        # Risk: nulls last via CASE so rows without a score sink to the bottom.
        "risk_desc":       case(
            (AISystem.current_risk_score.is_(None), 1), else_=0
        ).asc().nullslast(),
    }
    sort_expr = sort_clauses.get(sort, AISystem.created_at.desc())
    if sort == "risk_desc":
        stmt = stmt.order_by(sort_expr, AISystem.current_risk_score.desc().nullslast())
    else:
        stmt = stmt.order_by(sort_expr)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()

    return Page[AISystemListItem](
        items=[AISystemListItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


# ---------- detail / mutation ----------

@router.post("/systems", response_model=AISystemDetail, status_code=status.HTTP_201_CREATED)
async def create_system(
    payload: AISystemCreate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> AISystemDetail:
    system = AISystem(
        tenant_id=user.tenant_id,
        created_by=None,  # populated after user records exist in DB; Phase 0 has no /users/me write yet
        updated_by=None,
        discovery_sources=["manual"],
        **payload.model_dump(exclude_unset=False),
    )
    db.add(system)
    await db.flush()
    await db.refresh(system)
    return AISystemDetail.model_validate(system)


@router.get("/systems/{system_id}", response_model=AISystemDetail)
async def get_system(system_id: UUID, db: DBSession, user: CurrentUser) -> AISystemDetail:  # noqa: ARG001
    row = (await db.execute(select(AISystem).where(AISystem.id == system_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AI system not found")
    return AISystemDetail.model_validate(row)


@router.patch("/systems/{system_id}", response_model=AISystemDetail)
async def update_system(
    system_id: UUID,
    payload: AISystemUpdate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> AISystemDetail:
    row = (await db.execute(select(AISystem).where(AISystem.id == system_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AI system not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.refresh(row)
    return AISystemDetail.model_validate(row)


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_system(
    system_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> None:
    """Soft delete — sets status=decommissioned. Hard delete is intentionally not exposed."""
    row = (await db.execute(select(AISystem).where(AISystem.id == system_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AI system not found")
    row.status = "decommissioned"
    await db.flush()


# ---------- bulk operations ----------

class _BulkIds(BaseModel):  # type: ignore[name-defined]  # imported below
    ids: list[UUID] = Field(..., min_length=1, max_length=500)


class _BulkResult(BaseModel):  # type: ignore[name-defined]
    affected: int
    skipped:  int = 0
    reason:   str | None = None


@router.post("/systems/bulk-archive", response_model=_BulkResult)
async def bulk_archive_systems(
    payload: "_BulkIds",
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> "_BulkResult":
    """Soft-archive a batch of AI systems in one transaction. Same
    semantics as the per-row DELETE — status flips to decommissioned;
    no row is hard-deleted. Bounded to 500 IDs per call so a runaway
    selection can't load the whole tenant into memory."""
    affected = skipped = 0
    rows = (await db.execute(
        select(AISystem).where(AISystem.id.in_(payload.ids))
    )).scalars().all()
    seen = {r.id for r in rows}
    for r in rows:
        r.status = "decommissioned"
        affected += 1
    skipped = len(payload.ids) - len(seen)
    await db.flush()
    return _BulkResult(affected=affected, skipped=skipped)


@router.get("/systems/_/export.csv")
async def export_systems_csv(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
):
    """Stream the tenant's AI Registry as a CSV for offline review +
    auditor evidence packs. Same fields as the JSON list endpoint."""
    from fastapi.responses import StreamingResponse
    import csv, io
    rows = (await db.execute(
        select(AISystem).order_by(AISystem.first_discovered_at.desc())
    )).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "id", "name", "category", "subcategory", "intended_purpose",
        "owner_user_id", "department_id", "current_risk_score",
        "risk_level", "completeness_score", "is_shadow", "status",
        "policy_status", "aisia_status", "eu_ai_act_category",
        "first_discovered_at", "last_seen_at",
        "discovery_sources", "tags",
    ])
    for r in rows:
        w.writerow([
            r.id, r.name, r.category, r.subcategory, r.intended_purpose,
            r.owner_user_id, r.department_id, r.current_risk_score,
            r.risk_level, r.completeness_score, r.is_shadow, r.status,
            r.policy_status, r.aisia_status, r.eu_ai_act_category,
            r.first_discovered_at, r.last_seen_at,
            ";".join(r.discovery_sources or []),
            ";".join(r.tags or []),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aegis-registry.csv"'},
    )


# ---------- from-catalogue quick-add ----------

@router.post("/systems/from-catalogue", response_model=AISystemDetail,
             status_code=status.HTTP_201_CREATED)
async def from_catalogue(
    payload: FromCatalogueRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> AISystemDetail:
    """Pre-populate a registry record from a catalogue service. Returns the partial system."""
    svc = (
        await db.execute(select(AIService).where(AIService.id == payload.catalogue_service_id))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Catalogue service not found")

    system = AISystem(
        tenant_id=user.tenant_id,
        name=svc.name,
        catalogue_service_id=svc.id,
        provider_id=svc.provider_id,
        category=svc.category,
        subcategory=svc.subcategory,
        eu_ai_act_category=svc.eu_ai_act_cat,
        deployment_type=payload.deployment_type or "cloud_saas",
        department_id=payload.department_id,
        owner_user_id=payload.owner_user_id,
        intended_purpose=payload.intended_purpose,
        discovery_sources=["manual"],
        tags=svc.tags.copy() if svc.tags else [],
    )
    db.add(system)
    await db.flush()
    await db.refresh(system)
    return AISystemDetail.model_validate(system)


# ---------- stats ----------

@router.get("/stats", response_model=RegistryStats)
async def stats(db: DBSession, user: CurrentUser) -> RegistryStats:  # noqa: ARG001
    total = (await db.execute(select(func.count(AISystem.id)))).scalar_one()
    shadow = (await db.execute(
        select(func.count(AISystem.id)).where(AISystem.is_shadow.is_(True))
    )).scalar_one()
    avg = (await db.execute(select(func.avg(AISystem.completeness_score)))).scalar_one() or 0
    pending = (await db.execute(
        select(func.count(AISystem.id)).where(AISystem.aisia_status == "not_started")
    )).scalar_one()

    by_risk = dict((r, n) for r, n in (await db.execute(
        select(AISystem.risk_level, func.count(AISystem.id)).group_by(AISystem.risk_level)
    )).all())
    by_cat = dict((r, n) for r, n in (await db.execute(
        select(AISystem.category, func.count(AISystem.id)).group_by(AISystem.category)
    )).all())
    by_status = dict((r, n) for r, n in (await db.execute(
        select(AISystem.status, func.count(AISystem.id)).group_by(AISystem.status)
    )).all())

    return RegistryStats(
        total=total,
        shadow_count=shadow,
        completeness_avg=float(round(avg, 1)),
        by_risk_level=by_risk,
        by_category=by_cat,
        by_status=by_status,
        aisia_pending_count=pending,
    )
