"""BaseConnector + registry for IdP / Cloud / SaaS integrations.

Architecture
============

Each external system (Entra ID, Okta, AWS, Azure, GCP, M365, Google Workspace,
Salesforce, …) implements two methods:

  - ``test(credentials)`` — perform a cheap probe and return ok/error.
  - ``sync(credentials, tenant_id, integration_id, session)`` — run a full
    discovery pass and return :class:`SyncResult`.

Concrete implementations live under ``app/integrations/connectors/<vendor>/``
and call ``@register_connector("integration_id", kind=...)``.
"""
from __future__ import annotations

import abc
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

ConnectorKind = Literal["idp", "cloud", "saas"]


@dataclass(slots=True)
class SyncResult:
    """Outcome of a single connector sync run."""
    ok: bool
    discovered_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# Registry --------------------------------------------------------------------

_CONNECTORS: dict[str, type["BaseConnector"]] = {}


def register_connector(integration: str, *, kind: ConnectorKind):
    """Decorator that registers a connector against the ``integration`` key
    used on every :class:`IntegrationCredential` row.

    Example::

        @register_connector("entra_id", kind="idp")
        class EntraIdConnector(BaseConnector):
            ...
    """
    def _decorator(cls: type["BaseConnector"]) -> type["BaseConnector"]:
        cls.integration = integration
        cls.kind = kind
        if integration in _CONNECTORS:
            raise RuntimeError(f"Duplicate connector registration: {integration!r}")
        _CONNECTORS[integration] = cls
        return cls
    return _decorator


def get_connector(integration: str) -> "BaseConnector":
    cls = _CONNECTORS.get(integration)
    if cls is None:
        raise KeyError(f"No connector registered for {integration!r}. "
                       f"Available: {sorted(_CONNECTORS)}")
    return cls()


def list_connectors() -> dict[str, dict[str, str]]:
    return {
        integ: {"kind": cls.kind, "class": cls.__name__, "doc": (cls.__doc__ or "").strip().split("\n")[0]}
        for integ, cls in _CONNECTORS.items()
    }


def load_all_connectors() -> None:
    """Import every vendor submodule so @register_connector decorators fire."""
    import app.integrations.connectors as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.ispkg:
            try:
                importlib.import_module(f"app.integrations.connectors.{mod.name}.connector")
            except ModuleNotFoundError:
                # Vendor without a connector yet — placeholder package, skip.
                continue
        elif mod.name == "_stubs":
            # Bundled stubs for connectors whose full implementation is pending.
            importlib.import_module("app.integrations.connectors._stubs")


# Base class ------------------------------------------------------------------

class BaseConnector(abc.ABC):
    """Abstract base for every IdP/Cloud/SaaS connector."""

    integration: ClassVar[str]
    kind: ClassVar[ConnectorKind]

    @abc.abstractmethod
    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        """Cheap connectivity test — does NOT write anything to AEGIS DB.

        Return :class:`SyncResult(ok=True, ...)` on success;
        :class:`SyncResult(ok=False, error="…")` on auth/connectivity failure.
        """

    @abc.abstractmethod
    async def sync(
        self,
        credentials: dict[str, Any],
        *,
        tenant_id,
        integration_id,
        session,
    ) -> SyncResult:
        """Full discovery pass. Insert/update OAuthGrants or CloudAIResources
        as appropriate. Must be idempotent — re-running on the same tenant
        upserts, never duplicates."""
