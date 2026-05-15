"""Policy management + violations endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select

from app.core.deps import CurrentUser, DBSession, require_admin
from app.models.ai_system import AISystem
from app.models.policy import Policy
from app.models.policy_violation import PolicyViolation
from app.schemas.risk_policy import (
    PolicyCreate,
    PolicyDetail,
    PolicyReorderRequest,
    PolicyTemplateBrief,
    PolicyTestRequest,
    PolicyTestResponse,
    PolicyUpdate,
    ViolationResolve,
    ViolationRow,
)
from app.services.policy_engine import VALID_ACTIONS, evaluate

router = APIRouter(tags=["policies"])

# Policy templates live in the catalogue. Mounted via docker-compose at /workspace.
_TEMPLATE_DIRS = (
    Path("/workspace/catalogue/policy-templates"),
    Path(__file__).resolve().parents[3] / "catalogue" / "policy-templates",
)


# ---------- policies ----------

@router.get("/policies", response_model=list[PolicyDetail])
async def list_policies(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(
        select(Policy).order_by(Policy.priority.asc())
    )).scalars().all()
    return [PolicyDetail.model_validate(r) for r in rows]


@router.post("/policies", response_model=PolicyDetail, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> PolicyDetail:
    if payload.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400,
                            detail=f"Invalid action; must be one of {sorted(VALID_ACTIONS)}")
    row = Policy(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority,
        conditions=payload.conditions,
        action=payload.action,
        action_config=payload.action_config,
        is_active=payload.is_active,
        template_id=payload.template_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return PolicyDetail.model_validate(row)


@router.get("/policies/{policy_id}", response_model=PolicyDetail)
async def get_policy(policy_id: UUID, db: DBSession, user: CurrentUser) -> PolicyDetail:  # noqa: ARG001
    row = (await db.execute(select(Policy).where(Policy.id == policy_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return PolicyDetail.model_validate(row)


@router.patch("/policies/{policy_id}", response_model=PolicyDetail)
async def update_policy(
    policy_id: UUID,
    payload: PolicyUpdate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> PolicyDetail:
    row = (await db.execute(select(Policy).where(Policy.id == policy_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return PolicyDetail.model_validate(row)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> None:
    row = (await db.execute(select(Policy).where(Policy.id == policy_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(row)


@router.post("/policies/{policy_id}/test", response_model=PolicyTestResponse)
async def test_policy(
    policy_id: UUID,
    payload: PolicyTestRequest,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> PolicyTestResponse:
    """Evaluate a single policy against a specific system. Doesn't touch
    other policies — purely a dry-run of the supplied policy's conditions."""
    pol = (await db.execute(select(Policy).where(Policy.id == policy_id))).scalar_one_or_none()
    if pol is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    system = (await db.execute(
        select(AISystem).where(AISystem.id == payload.ai_system_id)
    )).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="AI system not found")

    from app.services.policy_engine import evaluate_conditions
    matched, keys = evaluate_conditions(pol.conditions or {}, system=system,
                                        user_groups=payload.user_groups)
    return PolicyTestResponse(
        action=pol.action if matched else "allow",
        policy_id=pol.id if matched else None,
        policy_name=pol.name if matched else None,
        matched_conditions=keys,
        config=pol.action_config or {},
    )


@router.post("/policies/evaluate", response_model=PolicyTestResponse)
async def evaluate_for_system(
    payload: PolicyTestRequest,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> PolicyTestResponse:
    """Run the FULL policy chain against a system (priority order, first match wins)."""
    system = (await db.execute(
        select(AISystem).where(AISystem.id == payload.ai_system_id)
    )).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="AI system not found")
    decision = await evaluate(session=db, system=system, user_groups=payload.user_groups)
    return PolicyTestResponse(
        action=decision.action, policy_id=decision.policy_id,
        policy_name=decision.policy_name,
        matched_conditions=decision.matched_conditions,
        config=decision.config,
    )


@router.post("/policies/reorder", response_model=list[PolicyDetail])
async def reorder_policies(
    payload: PolicyReorderRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> list[PolicyDetail]:
    """Atomically re-prioritise policies. The supplied order is the new priority
    order (first = priority 1)."""
    # Two-pass to avoid violating the (tenant_id, priority) unique constraint:
    # pass 1 — shift everything into a high range; pass 2 — assign final values.
    for offset, pid in enumerate(payload.ordered_ids, start=10_000):
        row = (await db.execute(select(Policy).where(Policy.id == pid))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Policy {pid} not found")
        row.priority = offset
    await db.flush()
    for new_priority, pid in enumerate(payload.ordered_ids, start=1):
        row = (await db.execute(select(Policy).where(Policy.id == pid))).scalar_one_or_none()
        if row is not None:
            row.priority = new_priority
    await db.flush()
    rows = (await db.execute(
        select(Policy).order_by(Policy.priority.asc())
    )).scalars().all()
    return [PolicyDetail.model_validate(r) for r in rows]


# ---------- templates ----------

def _load_template_files() -> list[dict]:
    for d in _TEMPLATE_DIRS:
        if d.exists():
            return [yaml.safe_load(p.read_text(encoding="utf-8"))
                    for p in sorted(d.glob("*.yaml"))]
    return []


@router.get("/policies/templates", response_model=list[PolicyTemplateBrief])
async def list_templates(user: CurrentUser):  # noqa: ARG001
    out: list[PolicyTemplateBrief] = []
    for t in _load_template_files():
        out.append(PolicyTemplateBrief(
            id=t["id"], name=t["name"], description=t.get("description", ""),
            rule_count=len(t.get("rules", [])),
        ))
    return out


@router.post("/policies/templates/{template_id}/import", response_model=list[PolicyDetail])
async def import_template(
    template_id: str,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> list[PolicyDetail]:
    target = None
    for t in _load_template_files():
        if t["id"] == template_id:
            target = t
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id!r} not found")

    # Place imported rules ABOVE any existing tenant policies at the highest
    # priority (lowest numeric). Find current min priority.
    current_min = (await db.execute(
        select(Policy.priority).order_by(Policy.priority.asc()).limit(1)
    )).scalar_one_or_none()
    base = (current_min or 1) - len(target.get("rules", []))
    if base < 1:
        base = 1

    created: list[Policy] = []
    for i, rule in enumerate(target.get("rules", [])):
        row = Policy(
            tenant_id=user.tenant_id,
            name=rule.get("name"),
            description=rule.get("description"),
            priority=base + i,
            conditions=rule.get("conditions") or {},
            action=rule.get("action"),
            action_config=rule.get("action_config") or {},
            is_active=True,
            template_id=template_id,
            created_by=None,
        )
        db.add(row)
        created.append(row)
    await db.flush()
    for r in created:
        await db.refresh(r)
    return [PolicyDetail.model_validate(r) for r in created]


# ---------- violations ----------

@router.get("/violations", response_model=list[ViolationRow])
async def list_violations(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    resolved: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    stmt = select(PolicyViolation).order_by(desc(PolicyViolation.occurred_at)).limit(limit)
    if resolved is not None:
        stmt = stmt.where(PolicyViolation.resolved.is_(resolved))
    rows = (await db.execute(stmt)).scalars().all()
    return [ViolationRow.model_validate(r) for r in rows]


@router.patch("/violations/{violation_id}/resolve", response_model=ViolationRow)
async def resolve_violation(
    violation_id: UUID,
    payload: ViolationResolve,
    db: DBSession,
    user: CurrentUser,
) -> ViolationRow:
    row = (await db.execute(
        select(PolicyViolation).where(PolicyViolation.id == violation_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    row.resolved = True
    row.resolved_by = None  # operator UUID once user.id mapping exists
    row.resolved_at = datetime.now(timezone.utc)
    row.resolution_notes = payload.notes
    await db.flush()
    await db.refresh(row)
    return ViolationRow.model_validate(row)
