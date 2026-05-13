"""Shape tests for catalogue + registry API — exercise the routes with the
existing fake_user fixture but stub the DB session so we don't need testcontainers
yet (that lands with the integration suite in the Phase 2 follow-up).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.deps import get_current_user, get_db
from app.main import app


@pytest.fixture
def admin_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="kc-admin",
        email="admin@aegis.local",
        tenant_id=uuid4(),
        role="admin",
        full_name="Admin",
        groups=["aegis:admin"],
        raw_claims={},
    )


@pytest.fixture
def mock_db() -> AsyncSession:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
async def shape_client(admin_user: AuthenticatedUser, mock_db: AsyncSession):
    app.dependency_overrides[get_current_user] = lambda: admin_user

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_catalogue_services_404_for_missing(shape_client: AsyncClient, mock_db) -> None:
    # First execute() -> scalar_one_or_none() -> None means "not found"
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute.return_value = result
    resp = await shape_client.get("/v1/catalogue/services/does-not-exist")
    assert resp.status_code == 404


async def test_registry_create_validates_required_fields(shape_client: AsyncClient) -> None:
    # Missing required `name` and `category` -> 422
    resp = await shape_client.post("/v1/registry/systems", json={})
    assert resp.status_code == 422


async def test_registry_get_404_for_missing(shape_client: AsyncClient, mock_db) -> None:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute.return_value = result
    resp = await shape_client.get(f"/v1/registry/systems/{uuid4()}")
    assert resp.status_code == 404


async def test_registry_from_catalogue_404_when_service_missing(shape_client: AsyncClient, mock_db) -> None:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute.return_value = result
    resp = await shape_client.post(
        "/v1/registry/systems/from-catalogue",
        json={"catalogue_service_id": str(uuid4())},
    )
    assert resp.status_code == 404


async def test_registry_endpoints_require_auth() -> None:
    """Without overriding get_current_user, all registry endpoints must reject."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for path in [
            "/v1/registry/systems",
            "/v1/registry/stats",
            "/v1/catalogue/services",
            "/v1/catalogue/categories",
            "/v1/catalogue/providers",
        ]:
            resp = await ac.get(path)
            assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"
