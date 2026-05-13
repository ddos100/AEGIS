"""Async Redis client + pub/sub helpers for the discovery feed."""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    return _client


def discovery_channel(tenant_id: str) -> str:
    """Per-tenant pub/sub channel name for the discovery WebSocket feed."""
    return f"aegis:discovery:{tenant_id}"


async def publish_discovery(tenant_id: str, payload: dict[str, Any]) -> None:
    """Publish a single message to the tenant's discovery channel.

    The receiver side is :func:`app.routes.discovery_ws.ws_discovery`, which
    forwards each message to every connected WebSocket client.
    """
    r = get_redis()
    await r.publish(discovery_channel(tenant_id), json.dumps(payload, default=str))
