"""Pluggable connector framework for Phase 3 integrations (IdP / Cloud / SaaS).

Mirrors the network-normalizer framework — each connector subclasses
:class:`BaseConnector`, registers itself via :func:`register_connector`,
and the API + Celery workers dispatch by the ``integration`` string on
the credential row.

Auto-loaded at API + worker startup via :func:`load_all_connectors`.
"""
from app.integrations.connectors.base import (
    BaseConnector,
    ConnectorKind,
    SyncResult,
    get_connector,
    list_connectors,
    load_all_connectors,
    register_connector,
)

__all__ = [
    "BaseConnector",
    "ConnectorKind",
    "SyncResult",
    "get_connector",
    "list_connectors",
    "load_all_connectors",
    "register_connector",
]
