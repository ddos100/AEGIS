"""Pluggable normalizer framework for discovery vector log sources.

Architecture
============

Every supported source (Zscaler ZIA, Squid, Palo Alto PAN-OS, CrowdStrike Falcon,
SentinelOne, generic OCSF, generic CEF, …) implements :class:`BaseNormalizer`
and registers itself via the :func:`register` decorator. The ingest pipeline
looks up the normalizer by the ``source`` field on the incoming request and
parses each raw record into a :class:`NormalizedEvent`.

Adding a new source therefore requires only:

  1. A new module under ``app.integrations.network.<vendor>/normalizer.py``
     implementing ``BaseNormalizer.parse()``.
  2. A ``@register("vendor_id", vector="proxy"|"ngfw"|"dns"|"xdr_edr")``
     decoration on the class.
  3. The module must be imported once at startup so the decorator runs
     (see :mod:`app.integrations.network` package ``__init__`` for the
     auto-import via :func:`load_all_normalizers`).

The matching engine, Celery pipeline, and shadow AI detector are all source-
agnostic — they only see ``NormalizedEvent`` instances.
"""
from __future__ import annotations

import abc
import importlib
import pkgutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

VectorType = Literal[
    "network_telemetry",  # generic proxy / NGFW / DNS bucket
    "xdr_edr",            # endpoint detection telemetry
    "browser_ext",        # AEGIS Chrome extension
    "idp", "cloud", "saas", "code_repo", "manual",
]
IngestionMode = Literal["push", "pull"]


@dataclass(slots=True)
class NormalizedEvent:
    """Canonical form every normalizer must emit.

    Designed so the downstream pipeline (matcher → bulk insert → shadow-AI
    detector → WebSocket broadcaster) is source-agnostic. Optional fields
    default to ``None`` / 0 / empty.
    """

    occurred_at: datetime
    vector: VectorType
    source: str                                # e.g. "zscaler_nss", "crowdstrike", "squid"
    domain: str | None = None                  # raw hostname observed
    url_path: str | None = None                # path only (never query strings)
    user_email: str | None = None
    department: str | None = None
    source_ip: str | None = None
    hostname: str | None = None                # device hostname (relevant for XDR/EDR)
    process_name: str | None = None
    process_hash: str | None = None
    bytes_sent: int | None = None
    bytes_recv: int | None = None
    request_count: int = 1
    session_id: str | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def matchable_string(self) -> str:
        """The string handed to the Aho-Corasick matcher.

        Includes both the bare hostname and a hostname+path concatenation so
        catalogue patterns can match either form (e.g. ``api.openai.com`` *or*
        ``api.openai.com/v1/chat/completions``).
        """
        if not self.domain:
            return ""
        if self.url_path:
            return f"{self.domain}{self.url_path}"
        return self.domain


# Registry --------------------------------------------------------------------

_NORMALIZERS: dict[str, type["BaseNormalizer"]] = {}


def register(source: str, *, vector: VectorType, ingestion_mode: IngestionMode = "push"):
    """Decorator that registers a normalizer class against a source key.

    Example::

        @register("zscaler_nss", vector="network_telemetry")
        class ZscalerNormalizer(BaseNormalizer):
            ...
    """
    def _decorator(cls: type["BaseNormalizer"]) -> type["BaseNormalizer"]:
        cls.source = source
        cls.vector = vector
        cls.ingestion_mode = ingestion_mode
        if source in _NORMALIZERS:
            raise RuntimeError(f"Duplicate normalizer registration for source={source!r}")
        _NORMALIZERS[source] = cls
        return cls
    return _decorator


def get_normalizer(source: str) -> "BaseNormalizer":
    cls = _NORMALIZERS.get(source)
    if cls is None:
        raise KeyError(f"No normalizer registered for source={source!r}. "
                       f"Available: {sorted(_NORMALIZERS)}")
    return cls()


def registered_sources() -> dict[str, dict[str, str]]:
    """Inventory of registered normalizers — used by the docs/help endpoint."""
    return {
        src: {"vector": cls.vector, "mode": cls.ingestion_mode, "class": cls.__name__}
        for src, cls in _NORMALIZERS.items()
    }


def load_all_normalizers() -> None:
    """Import every vendor submodule so its @register decorator fires.

    Called once at API + worker startup. Safe to call multiple times — duplicate
    registrations raise.
    """
    import app.integrations.network as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.ispkg:
            try:
                importlib.import_module(f"app.integrations.network.{mod.name}.normalizer")
            except ModuleNotFoundError:
                # Skip vendors without a normalizer module yet (placeholders).
                continue


# Base class ------------------------------------------------------------------

class BaseNormalizer(abc.ABC):
    """Abstract base class — implementations declare a `source` and `vector`
    via the :func:`register` decorator, and implement :meth:`parse`.
    """

    source: ClassVar[str]
    vector: ClassVar[VectorType]
    ingestion_mode: ClassVar[IngestionMode] = "push"

    @abc.abstractmethod
    def parse(self, raw: Any) -> NormalizedEvent | None:
        """Convert one raw log record into a NormalizedEvent.

        Return ``None`` when the record cannot be interpreted (malformed, wrong
        version, non-AI traffic that the normalizer chooses to drop early — the
        downstream matcher still gets to decide for AI traffic). Do NOT raise
        on parse errors — the worker loop relies on ``None`` to skip cleanly.
        """

    # --- helpers shared across normalizers --------------------------------

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "", "-") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _split_url(url: str | None) -> tuple[str | None, str | None]:
        """Return (host, path-only) from a URL or host-or-URL string.

        Privacy-preserving: query strings are dropped, never preserved.
        """
        if not url:
            return None, None
        s = url.strip()
        # Strip scheme
        for prefix in ("https://", "http://"):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        # Strip user@ prefix
        if "@" in s.split("/", 1)[0]:
            s = s.split("@", 1)[1]
        host, _, rest = s.partition("/")
        # Drop port
        if ":" in host:
            host = host.split(":", 1)[0]
        path = "/" + rest.split("?", 1)[0].split("#", 1)[0] if rest else None
        return (host.lower() or None), path
