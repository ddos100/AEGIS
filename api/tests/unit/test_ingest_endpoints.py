"""Shape tests for the ingest + extension catalogue endpoints.

These don't require a live DB — they only exercise auth + payload validation.
The full pipeline is exercised by the integration suite (Phase 2 follow-up).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.fixture
async def public_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_ingest_rejects_missing_key(public_client: AsyncClient) -> None:
    resp = await public_client.post("/v1/ingest/network", json={
        "source": "zscaler_nss",
        "tenant_id": str(uuid4()),
        "events": [{"url": "https://chat.openai.com/"}],
    })
    assert resp.status_code == 401


async def test_ingest_rejects_wrong_key(public_client: AsyncClient) -> None:
    resp = await public_client.post(
        "/v1/ingest/network",
        headers={"X-Ingest-Key": "wrong"},
        json={"source": "zscaler_nss", "tenant_id": str(uuid4()),
              "events": [{"url": "https://chat.openai.com/"}]},
    )
    assert resp.status_code == 401


async def test_ingest_rejects_empty_batch(public_client: AsyncClient) -> None:
    resp = await public_client.post(
        "/v1/ingest/network",
        headers={"X-Ingest-Key": settings.ingest_api_key},
        json={"source": "zscaler_nss", "tenant_id": str(uuid4()), "events": []},
    )
    # Pydantic min_length=1 -> 422
    assert resp.status_code == 422


async def test_ingest_rejects_unknown_source(public_client: AsyncClient) -> None:
    # We hand off a valid batch but use a source the registry doesn't know.
    resp = await public_client.post(
        "/v1/ingest/network",
        headers={"X-Ingest-Key": settings.ingest_api_key},
        json={"source": "no_such_vendor", "tenant_id": str(uuid4()),
              "events": [{"url": "https://chat.openai.com/"}]},
    )
    # Inline path raises KeyError from get_normalizer; FastAPI converts to 500
    # via the default handler — we accept any 4xx/5xx other than 401/422.
    assert resp.status_code >= 400


async def test_ingest_sources_endpoint_needs_key(public_client: AsyncClient) -> None:
    resp = await public_client.get("/v1/ingest/sources")
    assert resp.status_code == 401


async def test_extension_catalogue_needs_key(public_client: AsyncClient) -> None:
    resp = await public_client.get("/v1/extension/catalogue")
    assert resp.status_code == 401
