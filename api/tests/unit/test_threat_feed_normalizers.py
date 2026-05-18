"""Threat-feed normalizer unit tests.

Drives each registered normalizer against its bundled fixture and
asserts the shape of the produced DraftThreat. Network is not touched.
"""
from __future__ import annotations

import asyncio

import pytest

from app.integrations.threat_feeds import (
    DraftThreat,
    get_normalizer,
    list_normalizers,
)


def _collect(source: str) -> list[DraftThreat]:
    norm = get_normalizer(source)

    async def _go() -> list[DraftThreat]:
        out: list[DraftThreat] = []
        async for raw in norm.fetch():
            d = norm.normalize(raw)
            if d is not None:
                out.append(d)
        return out

    return asyncio.run(_go())


def test_three_sources_registered() -> None:
    sources = {s["source"] for s in list_normalizers()}
    assert {"mitre_atlas", "osv", "aiid"} <= sources


def test_mitre_atlas_skips_deprecated() -> None:
    drafts = _collect("mitre_atlas")
    ids = {d.threat_id for d in drafts}
    # Deprecated AML.T9999 must be skipped
    assert all("9999" not in i for i in ids)
    # The three live techniques in the fixture must produce drafts
    assert len(drafts) == 3
    for d in drafts:
        assert d.threat_id.startswith("AEGIS-T-ATLAS-")
        assert d.severity in {"critical", "high", "medium", "low"}
        assert d.classes
        assert d.vectors
        assert d.exposure_check == {}  # forces reviewer to add a predicate


def test_mitre_atlas_keyword_mapping() -> None:
    """The prompt-injection ATLAS technique should map to the right class."""
    drafts = _collect("mitre_atlas")
    by_id = {d.threat_id: d for d in drafts}
    pi = next(
        (d for d in drafts if "AML.T0051" in d.mitre_atlas_ids), None
    )
    assert pi is not None
    assert "indirect_prompt_injection" in pi.classes


def test_osv_filters_to_ai_packages_only() -> None:
    drafts = _collect("osv")
    # Three records in fixture; the `requests` one must be filtered.
    assert len(drafts) == 2
    titles = " ".join(d.title for d in drafts)
    assert "requests" not in titles
    for d in drafts:
        assert d.threat_id.startswith("AEGIS-T-OSV-")
        assert "supply_chain" in d.classes


def test_aiid_emits_three_drafts_with_classifications() -> None:
    drafts = _collect("aiid")
    assert len(drafts) == 3
    by_title = {d.title: d for d in drafts}
    assert any("Deepfake" in t for t in by_title)
    assert any("Autonomous" in t for t in by_title)
    assert any("vector store" in t.lower() for t in by_title)

    for d in drafts:
        assert d.threat_id.startswith("AEGIS-T-AIID-")
        assert d.classes
        assert d.vectors


def test_fingerprint_stable_across_runs() -> None:
    n = get_normalizer("mitre_atlas")
    f1 = n.fingerprint_of("AML.T0051")
    f2 = n.fingerprint_of("AML.T0051")
    assert f1 == f2
    assert len(f1) == 64


def test_payload_sha_is_content_addressed() -> None:
    n = get_normalizer("mitre_atlas")
    a = n.payload_sha_of({"id": "AML.T0001", "name": "x"})
    b = n.payload_sha_of({"name": "x", "id": "AML.T0001"})  # key order swap
    assert a == b
    c = n.payload_sha_of({"id": "AML.T0001", "name": "y"})
    assert a != c


def test_unknown_source_raises() -> None:
    with pytest.raises(KeyError):
        get_normalizer("nope")
