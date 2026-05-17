"""Validate every catalogue/threats/**/*.yaml against schema.yaml.

Run:
    python catalogue/scripts/threats_validate.py

CI runs this on every PR; pre-commit runs it on staged threat files.
Failure exit code is 1 if any record fails validation, otherwise 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
import jsonschema

ROOT = Path(__file__).resolve().parents[1] / "threats"
SCHEMA_FILE = ROOT / "schema.yaml"


def _load_schema() -> dict:
    with SCHEMA_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _iter_threat_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.yaml") if p.name != "schema.yaml")


def main() -> int:
    schema = _load_schema()
    files = _iter_threat_files()
    if not files:
        print("[threats_validate] no threat files yet — catalogue is empty")
        return 0

    errors: list[str] = []
    ids: dict[str, Path] = {}

    for path in files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            errors.append(f"[YAML] {path.relative_to(ROOT)}: {exc}")
            continue

        try:
            jsonschema.validate(instance=doc, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"[SCHEMA] {path.relative_to(ROOT)}: {exc.message}")
            continue

        tid = doc.get("threat_id")
        if tid in ids:
            errors.append(
                f"[DUPE] {path.relative_to(ROOT)}: threat_id {tid!r} "
                f"already declared in {ids[tid].relative_to(ROOT)}"
            )
        else:
            ids[tid] = path

    print(f"Checked {len(files)} threat files, {len(errors)} errors, "
          f"{len(ids)} unique threat_ids.")
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
