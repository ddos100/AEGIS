"""AISIA workflow endpoints (ISO 42001 Clause 6.1.2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select

from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst
from app.integrations.claude.client import generate_aisia_draft
from app.models.ai_system import AISystem
from app.models.aisia_record import AISIARecord
from app.schemas.risk_policy import AISIADetail, AISIAUpdate

router = APIRouter(prefix="/aisia", tags=["aisia"])


@router.get("", response_model=list[AISIADetail])
async def list_aisia(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    stmt = select(AISIARecord).order_by(desc(AISIARecord.updated_at)).limit(limit)
    if status_:
        stmt = stmt.where(AISIARecord.status.in_(status_))
    rows = (await db.execute(stmt)).scalars().all()
    return [AISIADetail.model_validate(r) for r in rows]


@router.post("/systems/{system_id}", response_model=AISIADetail, status_code=status.HTTP_201_CREATED)
async def initiate_aisia(
    system_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> AISIADetail:
    """Create an AISIA record for a system (if one doesn't exist yet)."""
    system = (await db.execute(
        select(AISystem).where(AISystem.id == system_id)
    )).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="AI system not found")

    existing = (await db.execute(
        select(AISIARecord).where(AISIARecord.ai_system_id == system_id)
    )).scalar_one_or_none()
    if existing is not None:
        return AISIADetail.model_validate(existing)

    row = AISIARecord(
        tenant_id=system.tenant_id,
        ai_system_id=system.id,
        status="initiated",
        initiated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    # Reflect on the system row so the Registry / Discovery UIs surface it
    system.aisia_status = "initiated"
    await db.flush()
    await db.refresh(row)
    return AISIADetail.model_validate(row)


@router.get("/{aisia_id}", response_model=AISIADetail)
async def get_aisia(aisia_id: UUID, db: DBSession, user: CurrentUser) -> AISIADetail:  # noqa: ARG001
    row = (await db.execute(
        select(AISIARecord).where(AISIARecord.id == aisia_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AISIA record not found")
    return AISIADetail.model_validate(row)


@router.patch("/{aisia_id}", response_model=AISIADetail)
async def update_aisia(
    aisia_id: UUID,
    payload: AISIAUpdate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> AISIADetail:
    row = (await db.execute(
        select(AISIARecord).where(AISIARecord.id == aisia_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AISIA record not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)

    # Mirror status onto the parent system row.
    system = (await db.execute(
        select(AISystem).where(AISystem.id == row.ai_system_id)
    )).scalar_one_or_none()
    if system is not None:
        system.aisia_status = row.status
        if row.impact_level:
            system.aisia_impact_level = row.impact_level
    await db.flush()
    await db.refresh(row)
    return AISIADetail.model_validate(row)


@router.post("/{aisia_id}/submit", response_model=AISIADetail)
async def submit_for_review(
    aisia_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> AISIADetail:
    row = await _get(db, aisia_id)
    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)
    await _mirror_status(db, row)
    await db.flush()
    await db.refresh(row)
    return AISIADetail.model_validate(row)


@router.post("/{aisia_id}/approve", response_model=AISIADetail)
async def approve(
    aisia_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> AISIADetail:
    row = await _get(db, aisia_id)
    row.status = "approved"
    row.approved_at = datetime.now(timezone.utc)
    await _mirror_status(db, row)
    await db.flush()
    await db.refresh(row)
    return AISIADetail.model_validate(row)


@router.post("/{aisia_id}/reject", response_model=AISIADetail)
async def reject(
    aisia_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> AISIADetail:
    row = await _get(db, aisia_id)
    row.status = "rejected"
    await _mirror_status(db, row)
    await db.flush()
    await db.refresh(row)
    return AISIADetail.model_validate(row)


@router.get("/{aisia_id}/draft", response_model=dict)
async def get_draft(
    aisia_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
):
    """Generate a Claude-assisted AISIA draft. Cached on the record."""
    row = await _get(db, aisia_id)
    if row.ai_draft:
        return {"draft": row.ai_draft, "cached": True}

    system = (await db.execute(
        select(AISystem).where(AISystem.id == row.ai_system_id)
    )).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="AI system not found")

    text = await generate_aisia_draft({
        "name":                   system.name,
        "category":               system.category,
        "intended_purpose":       system.intended_purpose,
        "output_type":            system.output_type,
        "data_types_processed":   list(system.data_types_processed or []),
        "affected_data_subjects": list(system.affected_data_subjects or []),
        "user_population":        system.user_population,
        "human_oversight_desc":   system.human_oversight_desc,
        "risk_level":             system.risk_level,
        "current_risk_score":     system.current_risk_score,
    })
    if text:
        row.ai_draft = text
        await db.flush()
        return {"draft": text, "cached": False}
    return {
        "draft": None,
        "cached": False,
        "fallback": ("Claude API not configured. Fill in each step manually using the prompts in "
                     "the wizard, then submit for review."),
    }


# ---------- helpers ----------

async def _get(db, aisia_id: UUID) -> AISIARecord:
    row = (await db.execute(
        select(AISIARecord).where(AISIARecord.id == aisia_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="AISIA record not found")
    return row


async def _mirror_status(db, row: AISIARecord) -> None:
    system = (await db.execute(
        select(AISystem).where(AISystem.id == row.ai_system_id)
    )).scalar_one_or_none()
    if system is not None:
        system.aisia_status = row.status
        if row.impact_level:
            system.aisia_impact_level = row.impact_level
