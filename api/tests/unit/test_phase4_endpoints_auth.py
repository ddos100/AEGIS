"""Auth-gating sanity tests for the Phase 4 endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def public_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_phase4_endpoints_require_auth(public_client: AsyncClient) -> None:
    for path in (
        "/v1/risk/summary",
        "/v1/aisia",
        "/v1/policies",
        "/v1/policies/templates",
        "/v1/violations",
    ):
        resp = await public_client.get(path)
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"
