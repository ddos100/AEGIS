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
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select, text

from app.core.auth import decode_token
from app.core.database import session_scope
from app.core.deps import CurrentUser, DBSession, require_admin
from app.core.redis import discovery_channel, get_redis, publish_discovery
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


@router.get("/discovery/oauth-grants")
async def list_oauth_grants(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    integration_id: UUID | None = None,
    matched_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Phase 3 — IdP-discovered OAuth grants. Filterable by integration."""
    from app.models.oauth_grant import OAuthGrant
    stmt = select(OAuthGrant).order_by(desc(OAuthGrant.last_seen_at)).limit(limit)
    if integration_id:
        stmt = stmt.where(OAuthGrant.integration_id == integration_id)
    if matched_only:
        stmt = stmt.where(OAuthGrant.catalogue_match.is_not(None))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "integration_id": str(r.integration_id),
            "app_id": r.app_id, "app_name": r.app_name,
            "app_publisher": r.app_publisher,
            "granted_scopes": r.granted_scopes,
            "catalogue_match": str(r.catalogue_match) if r.catalogue_match else None,
            "ai_system_id": str(r.ai_system_id) if r.ai_system_id else None,
            "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            "is_revoked": r.is_revoked,
        }
        for r in rows
    ]


@router.get("/discovery/cloud-resources")
async def list_cloud_resources(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    cloud_provider: str | None = None,
    resource_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Phase 3 — cloud AI inventory (Bedrock, SageMaker, Azure OpenAI, Vertex)."""
    from app.models.cloud_ai_resource import CloudAIResource
    stmt = select(CloudAIResource).order_by(desc(CloudAIResource.last_scanned_at)).limit(limit)
    if cloud_provider:
        stmt = stmt.where(CloudAIResource.cloud_provider == cloud_provider)
    if resource_type:
        stmt = stmt.where(CloudAIResource.resource_type == resource_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "cloud_provider": r.cloud_provider,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id, "resource_name": r.resource_name,
            "region": r.region, "account_id": r.account_id, "project_id": r.project_id,
            "service_name": r.service_name, "model_id": r.model_id,
            "status": r.status,
            "catalogue_match": str(r.catalogue_match) if r.catalogue_match else None,
            "ai_system_id": str(r.ai_system_id) if r.ai_system_id else None,
            "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
            "last_scanned_at": r.last_scanned_at.isoformat() if r.last_scanned_at else None,
        }
        for r in rows
    ]


@router.post("/discovery/test-broadcast")
async def test_broadcast(
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Publish a synthetic 'new_system' event on this tenant's discovery channel.

    Useful to verify the Shadow AI Radar wiring (WS proxy, JWT, Redis pub/sub)
    without firing a real ingest. Admin-only.
    """
    from uuid import uuid4
    payload = {
        "type": "new_system",
        "payload": {
            "id": str(uuid4()),
            "name": "Test Broadcast (no-op)",
            "category": "llm",
            "catalogue_slug": "test-broadcast",
            "first_discovered_at": datetime.now(timezone.utc).isoformat(),
            "vector": "manual",
            "detected_by_user": user.email,
            "department": "Test",
        },
    }
    await publish_discovery(str(user.tenant_id), payload)
    return {"published": True, "channel": discovery_channel(str(user.tenant_id))}


# ---------- WebSocket ----------

@router.websocket("/ws/discovery")
async def ws_discovery(websocket: WebSocket, token: str = ""):
    """Authenticated WebSocket — subscribe to the tenant's discovery channel.

    Auth: pass the user's JWT as a `?token=` query param (browsers can't set
    Authorization headers on WebSocket handshakes).
    """
    from app.core.logging import log
    if not token:
        log.warning("aegis.ws.connect_no_token", remote=websocket.client.host if websocket.client else None)
        await websocket.close(code=4401, reason="missing token")
        return
    try:
        user = await decode_token(token)
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.ws.connect_invalid_token", error=str(exc))
        await websocket.close(code=4401, reason="invalid token")
        return

    await websocket.accept()
    channel = discovery_channel(str(user.tenant_id))
    log.info("aegis.ws.connected", tenant_id=str(user.tenant_id), channel=channel)
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel)
    # Send a hello so the client knows the channel is live before any events flow.
    await websocket.send_text(json.dumps({
        "type": "connected",
        "payload": {"tenant_id": str(user.tenant_id), "channel": channel},
    }))
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
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        log.info("aegis.ws.disconnected", tenant_id=str(user.tenant_id), channel=channel)
