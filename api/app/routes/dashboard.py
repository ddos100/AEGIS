"""Dashboard aggregation endpoints (Phase 5)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, select
from typing import Annotated

from app.core.deps import CurrentUser, DBSession
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent
from app.models.aisia_record import AISIARecord
from app.models.compliance_framework import ComplianceFramework
from app.models.policy_violation import PolicyViolation
from app.schemas.compliance import (
    DashboardOverview,
    EcosystemEdge,
    EcosystemGraph,
    EcosystemNode,
    FrameworkScoreResp,
)
from app.services.compliance_engine import framework_score

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
async def overview(db: DBSession, user: CurrentUser):  # noqa: ARG001
    total = (await db.execute(select(func.count(AISystem.id)))).scalar_one()
    shadow = (await db.execute(
        select(func.count(AISystem.id)).where(AISystem.is_shadow.is_(True))
    )).scalar_one()
    by_level = dict(((lvl, n) for lvl, n in (await db.execute(
        select(AISystem.risk_level, func.count(AISystem.id))
        .group_by(AISystem.risk_level)
    )).all()))
    crit  = by_level.get("critical", 0)
    high  = by_level.get("high", 0)
    # Risk posture: weighted average of every system that actually has a
    # score. We count scored systems separately so the UI can distinguish
    # "0/100 because everything is genuinely low risk" from "haven't run
    # the risk engine yet" — the latter returns None, not 0.
    scored_systems = (await db.execute(
        select(func.count(AISystem.id)).where(AISystem.current_risk_score.is_not(None))
    )).scalar_one()
    avg_raw = (await db.execute(
        select(func.avg(AISystem.current_risk_score))
        .where(AISystem.current_risk_score.is_not(None))
    )).scalar_one()
    avg = float(avg_raw) if avg_raw is not None else None
    aisia_pending = (await db.execute(
        select(func.count(AISIARecord.id)).where(AISIARecord.status == "initiated")
    )).scalar_one()
    violations_open = (await db.execute(
        select(func.count(PolicyViolation.id)).where(PolicyViolation.resolved.is_(False))
    )).scalar_one()

    # Per-framework score (one row per active framework)
    fw_rows = (await db.execute(
        select(ComplianceFramework).where(ComplianceFramework.is_active.is_(True))
    )).scalars().all()
    framework_scores: list[FrameworkScoreResp] = []
    for fw in fw_rows:
        s = await framework_score(session=db, framework_slug=fw.slug)
        if s:
            framework_scores.append(FrameworkScoreResp(
                framework_id=s.framework_id, slug=s.slug, name=s.name,
                total_controls=s.total_controls, by_status=s.by_status,
                score_pct=s.score_pct, gaps=s.gaps[:5],   # short list for the dashboard
            ))

    top_risks = (await db.execute(
        select(AISystem.id, AISystem.name, AISystem.category,
               AISystem.current_risk_score, AISystem.risk_level, AISystem.is_shadow)
        .where(AISystem.current_risk_score.is_not(None))
        .order_by(desc(AISystem.current_risk_score)).limit(5)
    )).all()

    recent_since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_disc = (await db.execute(
        select(AIUsageEvent.occurred_at, AIUsageEvent.catalogue_slug,
               AIUsageEvent.vector, AISystem.name, AISystem.is_shadow)
        .join(AISystem, AISystem.id == AIUsageEvent.ai_system_id, isouter=True)
        .where(AIUsageEvent.occurred_at >= recent_since)
        .order_by(desc(AIUsageEvent.occurred_at)).limit(10)
    )).all()

    return DashboardOverview(
        risk_posture_score=(round(avg, 1) if avg is not None else None),
        scored_systems=scored_systems,
        total_systems=total, shadow_count=shadow,
        critical_count=crit, high_count=high,
        aisia_pending_count=aisia_pending,
        violations_open=violations_open,
        framework_scores=framework_scores,
        top_risks=[
            {"id": str(r.id), "name": r.name, "category": r.category,
             "score": r.current_risk_score, "level": r.risk_level,
             "is_shadow": r.is_shadow}
            for r in top_risks
        ],
        recent_discoveries=[
            {"occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
             "catalogue_slug": r.catalogue_slug, "vector": r.vector,
             "name": r.name, "is_shadow": r.is_shadow}
            for r in recent_disc
        ],
    )


@router.get("/ecosystem-map", response_model=EcosystemGraph)
async def ecosystem_map(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    """Nodes + edges for the D3 force-directed Ecosystem Map.

    Nodes = AI systems. Edges link systems in the same department
    (a coarse proxy for shared-data-flow until we model edges explicitly
    in a future phase).
    """
    rows = (await db.execute(
        select(AISystem.id, AISystem.name, AISystem.category,
               AISystem.risk_level, AISystem.is_shadow, AISystem.department_id)
        .order_by(desc(AISystem.current_risk_score)).limit(limit)
    )).all()
    # Usage counts per system (last 7d)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    usage_rows = (await db.execute(
        select(AIUsageEvent.ai_system_id, func.count(AIUsageEvent.id))
        .where(AIUsageEvent.occurred_at >= since)
        .group_by(AIUsageEvent.ai_system_id)
    )).all()
    usage_by_system = {r[0]: r[1] for r in usage_rows if r[0] is not None}

    nodes = [
        EcosystemNode(
            id=str(r.id), name=r.name, category=r.category,
            risk_level=r.risk_level, is_shadow=r.is_shadow,
            usage_count=usage_by_system.get(r.id, 0),
            department=str(r.department_id) if r.department_id else None,
        )
        for r in rows
    ]

    # Department edges
    by_dept: dict[str, list[str]] = {}
    for n in nodes:
        if n.department:
            by_dept.setdefault(n.department, []).append(n.id)
    edges: list[EcosystemEdge] = []
    for ids in by_dept.values():
        if len(ids) < 2:
            continue
        # Star: connect every id to the first (avoids O(n^2) full mesh)
        anchor = ids[0]
        for other in ids[1:]:
            edges.append(EcosystemEdge(source=anchor, target=other, kind="department"))

    return EcosystemGraph(nodes=nodes, edges=edges)
