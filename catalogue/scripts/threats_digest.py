"""Compute / verify the deterministic SHA-256 digest of the threat catalogue.

The digest is computed over the canonical JSON serialisation of every threat
YAML (sorted by threat_id), with keys sorted within each record. It is the
single auditable record of catalogue-state change: any intentional edit MUST
update catalogue/threats/.inventory_digest in the same commit.

Run:
    python catalogue/scripts/threats_digest.py            # prints current digest
    python catalogue/scripts/threats_digest.py --check    # compares against fixture
    python catalogue/scripts/threats_digest.py --update   # rewrites fixture
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "threats"
DIGEST_FILE = ROOT / ".inventory_digest"


def _load_threats() -> list[dict]:
    docs: list[dict] = []
    for path in sorted(p for p in ROOT.rglob("*.yaml") if p.name != "schema.yaml"):
        with path.open("r", encoding="utf-8") as fh:
            docs.append(yaml.safe_load(fh))
    return sorted(docs, key=lambda d: d["threat_id"])


def compute_digest() -> str:
    docs = _load_threats()
    canonical = json.dumps(docs, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check",  action="store_true")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)

    current = compute_digest()

    if args.update:
        DIGEST_FILE.write_text(current + "\n", encoding="utf-8")
        print(f"updated {DIGEST_FILE.relative_to(ROOT.parent.parent)} -> {current}")
        return 0

    if args.check:
        if not DIGEST_FILE.exists():
            print(f"FAIL: {DIGEST_FILE} missing — run --update")
            return 1
        pinned = DIGEST_FILE.read_text(encoding="utf-8").strip()
        if pinned != current:
            print(f"DRIFT: pinned={pinned} current={current}")
            return 1
        print(f"OK: digest matches ({current})")
        return 0

    print(current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
