"""Threat-feed ingest framework (Phase 7.2).

Every upstream source (MITRE ATLAS, OSV, AIID, OWASP LLM, HuggingFace,
PyPI, CERT-In, SCLLP internal research) implements `BaseFeedNormalizer`
and registers itself via `@register("source_slug")`. The scheduler
imports each module on startup and runs the registered normalizers
hourly via Celery beat.

Normalizer contract
-------------------
fetch()      -> Iterable[dict]    Pulls upstream records. Real-mode
                                  performs HTTP I/O; dev/test mode
                                  reads from a static fixture so CI
                                  doesn't depend on the internet.
normalize()  -> DraftThreat       Maps one upstream record to the
                                  canonical threat YAML shape used by
                                  catalogue/threats/.
upstream_id_of()                  Returns the source's stable ID for a
                                  record so dedup works across runs.

Privacy: normalizers never see PII. They only translate upstream
identifiers into our verbatim_description + source_ref + classes/vectors
mapping. The reviewer's edits stay in `draft_threats.draft` until they
explicitly publish.
"""
from app.integrations.threat_feeds.base import (
    BaseFeedNormalizer,
    DraftThreat,
    FeedFetchResult,
    get_normalizer,
    list_normalizers,
    register,
    load_all_feed_normalizers,
)
from app.integrations.threat_feeds import mitre_atlas  # noqa: F401  registration
from app.integrations.threat_feeds import osv          # noqa: F401
from app.integrations.threat_feeds import aiid         # noqa: F401

__all__ = [
    "BaseFeedNormalizer", "DraftThreat", "FeedFetchResult",
    "get_normalizer", "list_normalizers", "register",
    "load_all_feed_normalizers",
]
