"""Pytest fixtures.

We will swap in testcontainers-postgres for integration tests in Phase 0 follow-up;
for now we provide an in-memory HTTPX test client and a stub auth override.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.auth import AuthenticatedUser
from app.core.deps import get_current_user
from app.main import app


@pytest.fixture
def fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="kc-sub-test",
        email="tester@aegis.local",
        tenant_id=uuid.uuid4(),
        role="admin",
        full_name="Test User",
        groups=["aegis:admin"],
        raw_claims={},
    )


@pytest_asyncio.fixture
async def client(fake_user: AuthenticatedUser) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_current_user] = lambda: fake_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
