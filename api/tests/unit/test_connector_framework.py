"""Tests for the BaseConnector registry."""
from __future__ import annotations

import pytest

from app.integrations.connectors.base import (
    BaseConnector,
    SyncResult,
    get_connector,
    list_connectors,
    load_all_connectors,
    register_connector,
)

# Make sure the auto-load runs once.
load_all_connectors()


def test_every_bundled_integration_registered() -> None:
    inv = list_connectors()
    for expected in ("entra_id", "okta", "aws", "m365_copilot", "azure", "gcp", "google_workspace"):
        assert expected in inv, f"connector {expected!r} should be registered"


def test_get_connector_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_connector("no_such_integration")


def test_duplicate_registration_raises() -> None:
    """Registering the same source twice must fail loudly."""
    with pytest.raises(RuntimeError, match="Duplicate"):
        @register_connector("entra_id", kind="idp")
        class _Dup(BaseConnector):
            async def test(self, c): return SyncResult(ok=True)
            async def sync(self, c, *, tenant_id, integration_id, session):  # noqa: ARG002
                return SyncResult(ok=True)


def test_stubs_return_not_implemented_error() -> None:
    """Stub connectors must surface a clear error rather than appearing healthy."""
    import asyncio
    for integ in ("azure", "gcp", "google_workspace"):
        connector = get_connector(integ)
        result = asyncio.run(connector.test({}))
        assert result.ok is False
        assert "not yet implemented" in (result.error or "")
