"""Catalogue endpoints — global AI service catalogue + provider directory."""
from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DBSession  # noqa: F401 — CurrentUser enforces auth
from app.models.ai_provider import AIProvider
from app.models.ai_service import AIService
from app.schemas.catalogue import (
    AIServiceBrief,
    AIServiceDetail,
    CategoryStat,
    ProviderBrief,
)
from app.schemas.common import Page

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


@router.get("/services", response_model=Page[AIServiceBrief])
async def list_services(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001 — auth enforcement only
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
    q: str | None = None,
    category: str | None = None,
    provider_slug: str | None = None,
    include_inactive: bool = False,
) -> Page[AIServiceBrief]:
    stmt = select(AIService)
    if not include_inactive:
        stmt = stmt.where(AIService.is_active.is_(True))
    if category:
        stmt = stmt.where(AIService.category == category)
    if provider_slug:
        stmt = stmt.where(AIService.provider_slug == provider_slug)
    if q:
        pat = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AIService.name).like(pat),
                func.lower(AIService.description).like(pat),
                AIService.catalogue_id.ilike(pat),
            )
        )

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.order_by(AIService.name).offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()

    return Page[AIServiceBrief](
        items=[AIServiceBrief.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@router.get("/services/{catalogue_id}", response_model=AIServiceDetail)
async def get_service(catalogue_id: str, db: DBSession, user: CurrentUser) -> AIServiceDetail:  # noqa: ARG001
    row = (
        await db.execute(select(AIService).where(AIService.catalogue_id == catalogue_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Service not found in catalogue")
    return AIServiceDetail.model_validate(row)


@router.get("/categories", response_model=list[CategoryStat])
async def category_counts(db: DBSession, user: CurrentUser) -> list[CategoryStat]:  # noqa: ARG001
    rows = (
        await db.execute(
            select(AIService.category, func.count(AIService.id))
            .where(AIService.is_active.is_(True))
            .group_by(AIService.category)
            .order_by(func.count(AIService.id).desc())
        )
    ).all()
    return [CategoryStat(category=c, count=n) for c, n in rows]


@router.get("/providers", response_model=list[ProviderBrief])
async def list_providers(db: DBSession, user: CurrentUser) -> list[ProviderBrief]:  # noqa: ARG001
    rows = (await db.execute(select(AIProvider).order_by(AIProvider.name))).scalars().all()
    return [ProviderBrief.model_validate(r) for r in rows]
