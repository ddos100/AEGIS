"""Threat-feed routes — auth gate smoke tests."""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_feed_pending_unauthenticated() -> None:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/threats/feed/pending-review")
        assert resp.status_code == 401


async def test_feed_routes_registered(client: AsyncClient) -> None:
    resp = await client.get("/v1/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/threats/feed/sources" in paths
    assert "/v1/threats/feed/pending-review" in paths
    assert "/v1/threats/feed/drafts/{draft_id}" in paths
    assert "/v1/threats/feed/refresh" in paths
    assert "/v1/threats/feed/drafts/{draft_id}/publish" in paths
    assert "/v1/threats/feed/drafts/{draft_id}/reject" in paths
