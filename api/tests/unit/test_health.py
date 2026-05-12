"""Health endpoint smoke tests."""
from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["version"]


async def test_me_unauthenticated() -> None:
    """A request without overriding get_current_user should fail."""
    from httpx import ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/me")
        assert resp.status_code == 401


async def test_me_authenticated(client: AsyncClient) -> None:
    resp = await client.get("/v1/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "tester@aegis.local"
    assert body["role"] == "admin"
