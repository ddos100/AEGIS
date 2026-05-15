"""Auth-gating sanity for Phase 5 endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def public_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_phase5_endpoints_require_auth(public_client: AsyncClient) -> None:
    for path in (
        "/v1/compliance/frameworks",
        "/v1/compliance/mappings",
        "/v1/reports",
        "/v1/dashboard/overview",
        "/v1/dashboard/ecosystem-map",
    ):
        resp = await public_client.get(path)
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"


async def test_framework_yaml_files_present() -> None:
    """Quick filesystem sanity — all five expected YAMLs exist."""
    from pathlib import Path
    candidates = [
        Path("/workspace/catalogue/compliance-frameworks"),
        Path(__file__).resolve().parents[3] / "catalogue" / "compliance-frameworks",
    ]
    base = next((p for p in candidates if p.exists()), None)
    assert base is not None, "No framework dir mounted"
    for slug in ("iso_42001", "eu_ai_act", "nist_ai_rmf", "dpdpa",
                 "rbi_it_governance", "irdai_cybersecurity", "sebi_cscrf"):
        assert (base / f"{slug}.yaml").exists(), f"missing framework YAML: {slug}.yaml"
