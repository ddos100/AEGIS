"""Validate all catalogue YAML files against schemas/service.schema.yaml.

Usage: python -m catalogue.scripts.validate
Exit code 0 on success, 1 on any failure (used by CI).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "service.schema.yaml"
SERVICES_DIR = ROOT / "services"


def main() -> int:
    if not SCHEMA_PATH.exists():
        print(f"FATAL: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)

    errors_total = 0
    files_checked = 0
    ids_seen: dict[str, Path] = {}

    for yml in sorted(SERVICES_DIR.rglob("*.yaml")):
        files_checked += 1
        try:
            data = yaml.safe_load(yml.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"[YAML ERROR] {yml}: {e}", file=sys.stderr)
            errors_total += 1
            continue

        errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errs:
            for e in errs:
                path = "/".join(str(p) for p in e.path)
                print(f"[SCHEMA] {yml}: {path}: {e.message}", file=sys.stderr)
                errors_total += 1
            continue

        sid = data.get("id")
        if sid in ids_seen:
            print(f"[DUPLICATE ID] {sid} in {yml} (first seen at {ids_seen[sid]})", file=sys.stderr)
            errors_total += 1
        else:
            ids_seen[sid] = yml

    print(f"Checked {files_checked} files, {errors_total} errors, {len(ids_seen)} unique ids.")
    return 0 if errors_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
