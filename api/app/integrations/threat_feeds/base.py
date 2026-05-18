"""Base class + registry for threat-feed normalizers."""
from __future__ import annotations

import abc
import hashlib
import importlib
import json
import pkgutil
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar


@dataclass(slots=True)
class DraftThreat:
    """Normalised candidate threat record awaiting admin review.

    Matches the YAML shape under catalogue/threats/. Required fields
    map to the same names; optional fields use sensible defaults so a
    light upstream record still produces something the reviewer can
    publish without manual editing.
    """
    threat_id:               str
    title:                   str
    source_ref:              str
    verbatim_description:    str
    severity:                str            # critical | high | medium | low
    classes:                 list[str]
    vectors:                 list[str]
    description:             str | None = None
    mitre_atlas_ids:         list[str] = field(default_factory=list)
    owasp_llm_ids:           list[str] = field(default_factory=list)
    sector_amplifiers:       list[str] = field(default_factory=list)
    applies_to_jurisdictions: list[str] = field(default_factory=list)
    exposure_check:          dict[str, Any] = field(default_factory=dict)
    mitigation:              dict[str, Any] | None = None
    evidence_hints:          list[str] = field(default_factory=list)
    compliance_implications: list[str] = field(default_factory=list)
    catalogue_version:       str = "1.0.0"
    last_updated:            date = field(default_factory=date.today)

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__slots__}
        # date → str for JSON / YAML serialisation
        if isinstance(d.get("last_updated"), date):
            d["last_updated"] = d["last_updated"].isoformat()
        return d


@dataclass(slots=True)
class FeedFetchResult:
    raw_records:  list[dict[str, Any]]
    drafts:       list[DraftThreat]
    new_count:    int
    duplicate_count: int
    error: str | None = None


class BaseFeedNormalizer(abc.ABC):
    """Subclasses MUST declare `source` (class attr) and implement
    `fetch()` + `normalize(raw)`. Optional `applies_to_jurisdictions`
    default may be overridden per source."""

    source: ClassVar[str]
    default_jurisdictions: ClassVar[list[str]] = ["global"]

    @abc.abstractmethod
    async def fetch(self) -> AsyncIterator[dict[str, Any]]:
        """Yield raw upstream records as dicts.

        Implementations must be safe for repeat invocation; the ingest
        pipeline dedupes via `source_fingerprint`.
        """

    @abc.abstractmethod
    def normalize(self, raw: dict[str, Any]) -> DraftThreat | None:
        """Translate one upstream record to a DraftThreat. Return None
        when the record is irrelevant (e.g. an OSV CVE that doesn't
        touch AI ecosystem packages)."""

    # ------ helpers shared by all normalizers ------

    def upstream_id_of(self, raw: dict[str, Any]) -> str:
        """Stable identifier for dedup. Default uses 'id' / 'cve' /
        'attack_id' keys; sources can override."""
        return str(
            raw.get("id") or raw.get("cve") or raw.get("attack_id")
            or raw.get("number") or hashlib.sha256(
                json.dumps(raw, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
        )

    def fingerprint_of(self, upstream_id: str) -> str:
        return hashlib.sha256(f"{self.source}|{upstream_id}".encode()).hexdigest()

    def payload_sha_of(self, raw: dict[str, Any]) -> str:
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

_NORMALIZERS: dict[str, type["BaseFeedNormalizer"]] = {}


def register(source: str):
    def _decorator(cls: type["BaseFeedNormalizer"]) -> type["BaseFeedNormalizer"]:
        cls.source = source
        if source in _NORMALIZERS:
            raise RuntimeError(f"Duplicate feed normalizer for source={source!r}")
        _NORMALIZERS[source] = cls
        return cls
    return _decorator


def get_normalizer(source: str) -> BaseFeedNormalizer:
    cls = _NORMALIZERS.get(source)
    if cls is None:
        raise KeyError(f"No feed normalizer registered for source={source!r}")
    return cls()


def list_normalizers() -> list[dict[str, Any]]:
    return [
        {"source": s, "class": cls.__name__,
         "default_jurisdictions": list(cls.default_jurisdictions)}
        for s, cls in sorted(_NORMALIZERS.items())
    ]


def load_all_feed_normalizers() -> None:
    """Import every vendor submodule so @register decorators fire."""
    import app.integrations.threat_feeds as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.ispkg:
            try:
                importlib.import_module(f"app.integrations.threat_feeds.{mod.name}.normalizer")
            except ModuleNotFoundError:
                continue
