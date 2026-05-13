"""Discovery feed + usage analytics endpoints.

  GET  /v1/discovery/feed         Recent discovery events (paginated)
  GET  /v1/discovery/vectors      List discovery vector configurations
  GET  /v1/usage/summary          Aggregated usage from the continuous aggregate
  GET  /v1/usage/top-systems      Top-N AI systems by event count
  WS   /v1/ws/discovery           Real-time push (Redis pub/sub fan-out)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select, text

from app.core.auth import decode_token
from app.core.database import session_scope
from app.core.deps import CurrentUser, DBSession
from app.core.redis import discovery_channel, get_redis
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent
from app.models.discovery_vector import DiscoveryVector

router = APIRouter(tags=["discovery"])


@router.get("/discovery/feed")
async def feed(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    since_hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = (
        select(
            AIUsageEvent.occurred_at,
            AIUsageEvent.catalogue_slug,
            AIUsageEvent.ai_system_id,
            AIUsageEvent.vector,
            AIUsageEvent.source,
            AIUsageEvent.user_email,
            AIUsageEvent.department,
            AISystem.name,
            AISystem.category,
            AISystem.is_shadow,
        )
        .join(AISystem, AISystem.id == AIUsageEvent.ai_system_id, isouter=True)
        .where(AIUsageEvent.occurred_at >= since)
        .order_by(desc(AIUsageEvent.occurred_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "occurred_at": r.occurred_at.isoformat(),
            "catalogue_slug": r.catalogue_slug,
            "ai_system_id": str(r.ai_system_id) if r.ai_system_id else None,
            "name": r.name,
            "category": r.category,
            "vector": r.vector,
            "source": r.source,
            "user_email": r.user_email,
            "department": r.department,
            "is_shadow": r.is_shadow if r.is_shadow is not None else False,
        }
        for r in rows
    ]


@router.get("/discovery/vectors")
async def list_vectors(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(select(DiscoveryVector).order_by(DiscoveryVector.name))).scalars().all()
    return [
        {
            "id": str(v.id), "name": v.name, "source": v.source, "vector_type": v.vector_type,
            "status": v.status, "last_sync_at": v.last_sync_at.isoformat() if v.last_sync_at else None,
            "events_total": v.events_total, "last_error": v.last_error,
        }
        for v in rows
    ]


@router.get("/usage/summary")
async def usage_summary(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    since_hours: Annotated[int, Query(ge=1, le=720)] = 24,
):
    """Aggregated usage from the continuous aggregate (never the raw hypertable)."""
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    sql = text(
        """
        SELECT bucket, catalogue_slug, ai_system_id, vector,
               SUM(event_count)::bigint  AS event_count,
               SUM(unique_users)::bigint AS unique_users
        FROM ai_usage_hourly
        WHERE bucket >= :since
        GROUP BY bucket, catalogue_slug, ai_system_id, vector
        ORDER BY bucket DESC
        """
    )
    rows = (await db.execute(sql, {"since": since})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/usage/top-systems")
async def top_systems(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    since_hours: Annotated[int, Query(ge=1, le=720)] = 168,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = (
        select(
            AISystem.id, AISystem.name, AISystem.category, AISystem.is_shadow,
            func.count(AIUsageEvent.id).label("event_count"),
            func.count(func.distinct(AIUsageEvent.user_email)).label("unique_users"),
        )
        .join(AIUsageEvent, AIUsageEvent.ai_system_id == AISystem.id)
        .where(AIUsageEvent.occurred_at >= since)
        .group_by(AISystem.id)
        .order_by(desc("event_count"))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"id": str(r.id), "name": r.name, "category": r.category, "is_shadow": r.is_shadow,
         "event_count": r.event_count, "unique_users": r.unique_users}
        for r in rows
    ]


# ---------- WebSocket ----------

@router.websocket("/ws/discovery")
async def ws_discovery(websocket: WebSocket, token: str):
    """Authenticated WebSocket — subscribe to the tenant's discovery channel.

    Auth: pass the user's JWT as a `?token=` query param (browsers cannot set
    Authorization headers on WebSocket handshakes).
    """
    try:
        user = await decode_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    await websocket.accept()
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(discovery_channel(str(user.tenant_id)))
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode()
            try:
                await websocket.send_text(data)
            except WebSocketDisconnect:
                break
    finally:
        await pubsub.unsubscribe(discovery_channel(str(user.tenant_id)))
        await pubsub.close()
