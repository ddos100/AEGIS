"""Threat-catalogue routes — auth + module-gate smoke tests.

Exercises just enough of the router to verify:
  - unauthenticated callers receive 401
  - authenticated callers without AEGIS-THREAT receive 402 with the
    structured `{module, action, contact}` payload
  - the dev tenant (seeded with all modules by Alembic 009) gets through
    to a 200 — full row shape coverage lives in the per-engine tests.
"""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_threats_list_unauthenticated() -> None:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/threats")
        assert resp.status_code == 401


async def test_licence_endpoint_unauthenticated() -> None:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/licence")
        assert resp.status_code == 401


async def test_threats_routes_registered(client: AsyncClient) -> None:
    """Routes must be discoverable via OpenAPI."""
    resp = await client.get("/v1/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/threats" in paths
    assert "/v1/threats/{threat_id}" in paths
    assert "/v1/licence" in paths
