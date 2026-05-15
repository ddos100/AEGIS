"""Determinism guard for the compliance framework catalogue.

The platform's correctness claim — that the compliance module lists the
exact AI requirements without drift on consequential runs — rests on
two contracts:

  1. Every requirement_text in the YAML is a verbatim citation; the
     importer never paraphrases, never calls an LLM, never derives text.
  2. The byte-content of the loaded inventory is stable: same files
     in -> same digest out, on any host, any Python version, any day.

This test enforces (2). It loads every YAML file under
`catalogue/compliance-frameworks/`, computes the canonical SHA-256
digest, and asserts it equals the fixture in `.inventory_digest`.

When you intentionally change a framework YAML, update the fixture in
the same commit — the diff in the fixture is the single, reviewable
change record. Any drift caused by parser behaviour, ordering, or
inadvertent edits will fail this test loudly.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "catalogue" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_inventory_digest_matches_fixture() -> None:
    """The loaded catalogue must match the committed digest byte-for-byte."""
    import import_frameworks as imp

    docs = imp.load_docs(strict=True)
    actual = imp.inventory_digest(docs)

    fixture = (REPO_ROOT / "catalogue" / "compliance-frameworks" / ".inventory_digest").read_text(encoding="utf-8").strip()

    assert actual == fixture, (
        "Compliance inventory drift detected.\n"
        f"  Expected (fixture): {fixture}\n"
        f"  Actual   (loaded):  {actual}\n"
        "If this change is intentional, update "
        "catalogue/compliance-frameworks/.inventory_digest in the same commit."
    )


def test_every_control_has_source_ref_and_requirement_text() -> None:
    """No control should be missing the authoritative citation or verbatim text."""
    import import_frameworks as imp

    docs = imp.load_docs(strict=True)
    missing: list[str] = []
    for d in docs:
        for c in d["controls"]:
            if not c.get("source_ref"):
                missing.append(f"{d['slug']}/{c['control_id']}: source_ref")
            if not c.get("requirement_text"):
                missing.append(f"{d['slug']}/{c['control_id']}: requirement_text")
    assert not missing, "Controls missing verbatim citation:\n" + "\n".join(missing)


def test_control_ids_are_unique_within_each_framework() -> None:
    import import_frameworks as imp

    docs = imp.load_docs(strict=True)
    for d in docs:
        ids = [c["control_id"] for c in d["controls"]]
        assert len(ids) == len(set(ids)), f"Duplicate control_id in {d['slug']}: {ids}"
