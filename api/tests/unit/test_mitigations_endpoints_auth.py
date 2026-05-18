"""Mitigation routes — auth gate smoke tests."""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_mitigations_list_unauthenticated() -> None:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/mitigations")
        assert resp.status_code == 401


async def test_mitigations_routes_registered(client: AsyncClient) -> None:
    resp = await client.get("/v1/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/mitigations" in paths
    assert "/v1/mitigations/{mitigation_id}" in paths
    assert "/v1/mitigations/{mitigation_id}/approve" in paths
    assert "/v1/mitigations/{mitigation_id}/reject" in paths
    assert "/v1/mitigations/{mitigation_id}/dismiss" in paths
