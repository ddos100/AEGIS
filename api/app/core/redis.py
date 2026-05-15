"""Async Redis client + pub/sub helpers for the discovery feed.

Defensive: the client is configured with explicit socket timeouts and every
publish goes through ``asyncio.wait_for`` so a misbehaving Redis can never
hang a request handler. Connection failures are caught and logged — they
NEVER bubble up to the caller, because losing a Shadow AI Radar update is
preferable to dropping the actual ingest.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import log

_client: aioredis.Redis | None = None

# Hard cap on a single publish — anything longer means Redis is degraded.
PUBLISH_TIMEOUT_SECONDS = 2.0


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            # Don't let a hung connect/read silently block forever.
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            retry_on_timeout=False,
            health_check_interval=30,
        )
    return _client


def discovery_channel(tenant_id: str) -> str:
    """Per-tenant pub/sub channel name for the discovery WebSocket feed."""
    return f"aegis:discovery:{tenant_id}"


async def publish_discovery(tenant_id: str, payload: dict[str, Any]) -> bool:
    """Publish a single message to the tenant's discovery channel.

    Returns True on success, False on any failure (timeout, connect error,
    encode error). Never raises — callers can rely on this being non-fatal.
    """
    r = get_redis()
    channel = discovery_channel(tenant_id)
    try:
        body = json.dumps(payload, default=str)
        await asyncio.wait_for(r.publish(channel, body), timeout=PUBLISH_TIMEOUT_SECONDS)
        return True
    except asyncio.TimeoutError:
        log.warning("aegis.redis.publish_timeout", channel=channel,
                    timeout=PUBLISH_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — defensive catch on the hot path
        log.warning("aegis.redis.publish_failed", channel=channel,
                    error_type=type(exc).__name__, error=str(exc))
    return False
