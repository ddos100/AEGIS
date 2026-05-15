"""Endpoint-shape tests for /v1/integrations (Phase 3)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def public_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_unauthenticated_requests_get_401(public_client: AsyncClient) -> None:
    for path in (
        "/v1/integrations",
        "/v1/integrations/types",
        "/v1/discovery/oauth-grants",
        "/v1/discovery/cloud-resources",
    ):
        resp = await public_client.get(path)
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"
