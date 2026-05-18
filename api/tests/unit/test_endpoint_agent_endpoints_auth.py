"""Endpoint Agent routes — auth + payload-allowlist smoke tests."""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_devices_unauthenticated() -> None:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/endpoint-agent/devices")
        assert resp.status_code == 401


async def test_ingest_without_bearer_token() -> None:
    """The ingest endpoint must reject anonymous calls even though it
    isn't behind JWT — it requires the device's signed token."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/v1/ingest/endpoint-agent",
                              json={"device_id": "00000000-0000-0000-0000-000000000000",
                                    "events": []})
        assert resp.status_code == 401


async def test_routes_registered(client: AsyncClient) -> None:
    resp = await client.get("/v1/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/endpoint-agent/devices" in paths
    assert "/v1/endpoint-agent/enrollment-code" in paths
    assert "/v1/endpoint-agent/devices/{device_id}/revoke" in paths
    assert "/v1/endpoint-agent/events" in paths
    assert "/v1/endpoint-agent/enroll" in paths
    assert "/v1/ingest/endpoint-agent" in paths


async def test_pii_denylist_blocks_prompt_key() -> None:
    """Validator helper used by the route layer — directly exercised
    so the contract is locked even before a real device enrols."""
    from app.routes.endpoint_agent import _validate_payload
    bad = {"prompt": "hello", "process_name": "x"}
    reason = _validate_payload("process_exec", bad)
    assert reason is not None and "pii_shaped_key:prompt" in reason


async def test_validator_rejects_unexpected_keys() -> None:
    from app.routes.endpoint_agent import _validate_payload
    reason = _validate_payload("process_exec",
                                 {"process_name": "x", "extra_key": "y"})
    assert reason is not None and "unexpected_keys" in reason


async def test_validator_accepts_allowed_payload() -> None:
    from app.routes.endpoint_agent import _validate_payload
    ok = {
        "process_name": "ollama", "process_sha256": "a" * 64,
        "parent_process_name": "sh", "parent_process_sha256": "b" * 64,
        "command_line_sha256": "c" * 64,
    }
    assert _validate_payload("process_exec", ok) is None


async def test_validator_rejects_bare_path_key() -> None:
    """`path` (without `_pattern` suffix) is denylisted — agents must
    send `path_pattern` instead so absolute home paths never reach the
    backend."""
    from app.routes.endpoint_agent import _validate_payload
    reason = _validate_payload("file_write_to_watched_path",
                                 {"path": "/home/alice/.bashrc",
                                  "event_type": "modified",
                                  "new_mode": 0o600,
                                  "content_sha256": "d" * 64})
    assert reason is not None and "pii_shaped_key:path" in reason
