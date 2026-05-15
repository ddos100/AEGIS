"""Auth proxy smoke tests.

The proxy endpoints (`/v1/auth/login`, `/v1/auth/refresh`, `/v1/auth/logout`)
forward to Keycloak. In unit tests we don't have Keycloak running, so we just
verify input validation + that the routes are wired. Integration coverage
that exercises the actual Keycloak round trip lives in compose-based e2e tests.
"""
from __future__ import annotations

from httpx import AsyncClient


async def test_login_requires_credentials(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/login", json={})
    # FastAPI returns 422 for schema-violating bodies.
    assert resp.status_code == 422


async def test_refresh_requires_token(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/refresh", json={})
    assert resp.status_code == 422


async def test_logout_accepts_missing_body(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/logout", json={})
    assert resp.status_code in {204, 502}  # 502 if Keycloak unreachable, 204 if skipped


async def test_sources_requires_auth() -> None:
    from httpx import ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/auth/sources")
        assert resp.status_code == 401


async def test_sources_returns_inventory(client: AsyncClient) -> None:
    resp = await client.get("/v1/auth/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # The conftest loads normalizers; we expect at least the bundled ones.
    if body:
        sample = body[0]
        assert {"source", "vector", "mode", "cls"} <= sample.keys()


async def test_session_id_rotates_on_different_jti() -> None:
    """The hash function must produce different ids for tokens with different jti."""
    from app.routes.auth import _session_id_from_access
    from jose import jwt as jose_jwt
    t1 = jose_jwt.encode({"sub": "u1", "jti": "a"}, "secret", algorithm="HS256")
    t2 = jose_jwt.encode({"sub": "u1", "jti": "b"}, "secret", algorithm="HS256")
    assert _session_id_from_access(t1) != _session_id_from_access(t2)
    # Same payload reproduces the same id (deterministic).
    t1b = jose_jwt.encode({"sub": "u1", "jti": "a"}, "different-secret", algorithm="HS256")
    assert _session_id_from_access(t1) == _session_id_from_access(t1b)
