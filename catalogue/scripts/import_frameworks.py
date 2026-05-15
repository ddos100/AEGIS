"""Import compliance framework YAML files into compliance_frameworks +
compliance_controls.

Same invocation patterns as :mod:`catalogue.scripts.importer` —
runs from inside the api container OR from the repo root on the host.

  docker compose exec api python /workspace/catalogue/scripts/import_frameworks.py -v

Determinism guarantees
----------------------
- Files are sorted alphabetically before processing.
- Controls within each file are loaded in the order they appear in YAML.
- Upserts are keyed by `(framework_id, control_id)` so repeat runs are
  byte-for-byte identical at the DB level.
- A SHA-256 of the full normalised inventory (verbatim text + IDs + source
  refs) is computed and printed; this is the value to assert against in the
  determinism test fixture, and what the determinism CI check compares.
- The script never calls Claude or any LLM. All requirement text comes
  from the YAML files committed to git, which are themselves verbatim
  citations from the published source documents.

Idempotent: upserts by (framework_slug) and (framework_id, control_id).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator

HERE = Path(__file__).resolve()


def _find_paths() -> tuple[Path, Path]:
    root = HERE.parents[2]
    cat = root / "catalogue"
    if cat.exists():
        api_sibling = root / "api"
        if api_sibling.exists():
            sys.path.insert(0, str(api_sibling))
        return cat, cat / "compliance-frameworks" / "schema.yaml"
    cat = HERE.parents[1]
    return cat, cat / "compliance-frameworks" / "schema.yaml"


CATALOGUE_DIR, SCHEMA_PATH = _find_paths()
FRAMEWORKS_DIR = CATALOGUE_DIR / "compliance-frameworks"

# DB-touching imports are deferred so `load_docs` + `inventory_digest` can
# be used in pure-Python contexts (the determinism test, CI lint, etc.)
# without SQLAlchemy or the app.models package being importable.


def _connect():  # noqa: ANN202 — Session type imported lazily
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    url = os.environ.get("DATABASE_URL_SYNC", "postgresql+psycopg2://aegis:aegis@postgres:5432/aegis")
    return Session(create_engine(url, future=True), future=True)


def import_all(*, dry_run: bool = False, verbose: bool = False) -> int:
    # DB-touching imports lazy — see module docstring.
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.compliance_control import ComplianceControl
    from app.models.compliance_framework import ComplianceFramework

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)

    docs: list[dict[str, Any]] = []
    errors = 0
    for path in sorted(FRAMEWORKS_DIR.glob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"[YAML] {path}: {exc}", file=sys.stderr)
            errors += 1
            continue
        for err in sorted(validator.iter_errors(d), key=lambda e: tuple(str(p) for p in e.path)):
            print(f"[SCHEMA] {path}: {'/'.join(str(p) for p in err.path)}: {err.message}", file=sys.stderr)
            errors += 1
        else:
            docs.append(d)

    if errors:
        print(f"Refusing to import — {errors} files failed validation.", file=sys.stderr)
        return 1
    if dry_run:
        print(f"DRY RUN — {len(docs)} frameworks "
              f"({sum(len(d['controls']) for d in docs)} controls total) would be upserted.")
        return 0

    session = _connect()
    fw_created = fw_updated = ctrl_total = 0
    for d in docs:
        stmt = (
            pg_insert(ComplianceFramework)
            .values(
                slug=d["slug"], name=d["name"], version=d["version"],
                description=d.get("description"), authority=d.get("authority"),
                jurisdiction=d.get("jurisdiction"),
                is_active=d.get("is_active", True),
            )
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={
                    "name":         d["name"],
                    "version":      d["version"],
                    "description":  d.get("description"),
                    "authority":    d.get("authority"),
                    "jurisdiction": d.get("jurisdiction"),
                    "is_active":    d.get("is_active", True),
                },
            )
            .returning(ComplianceFramework.id)
        )
        framework_id = session.execute(stmt).scalar_one()
        # Detect create vs update — re-query (simpler than tracking xmax).
        existing = session.execute(
            select(ComplianceControl.id).where(ComplianceControl.framework_id == framework_id).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            fw_created += 1
        else:
            fw_updated += 1

        for ctrl in d["controls"]:
            cstmt = (
                pg_insert(ComplianceControl)
                .values(
                    framework_id=framework_id,
                    control_id=ctrl["control_id"],
                    title=ctrl["title"],
                    description=ctrl.get("description"),
                    requirement_text=ctrl.get("requirement_text"),
                    source_ref=ctrl.get("source_ref"),
                    category=ctrl.get("category"),
                    is_mandatory=ctrl.get("is_mandatory", True),
                    applies_to=ctrl.get("applies_to", []),
                    evidence_hints=ctrl.get("evidence_hints", []),
                    auto_check=ctrl.get("auto_check", {}),
                )
                .on_conflict_do_update(
                    constraint="uq_controls_control_id",
                    set_={
                        "title":            ctrl["title"],
                        "description":      ctrl.get("description"),
                        "requirement_text": ctrl.get("requirement_text"),
                        "source_ref":       ctrl.get("source_ref"),
                        "category":         ctrl.get("category"),
                        "is_mandatory":     ctrl.get("is_mandatory", True),
                        "applies_to":       ctrl.get("applies_to", []),
                        "evidence_hints":   ctrl.get("evidence_hints", []),
                        "auto_check":       ctrl.get("auto_check", {}),
                    },
                )
            )
            session.execute(cstmt)
            ctrl_total += 1
            if verbose:
                print(f"  {d['slug']:>22}  {ctrl['control_id']}")

    session.commit()
    digest = inventory_digest(docs)
    print(f"Frameworks: {fw_created} created / {fw_updated} updated. Controls: {ctrl_total}.")
    print(f"Inventory SHA-256: {digest}")
    return 0


# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------

def inventory_digest(docs: list[dict[str, Any]]) -> str:
    """Compute a stable SHA-256 over the framework + control inventory.

    Use this to detect drift across consequential runs: as long as the YAML
    files in catalogue/compliance-frameworks/ are unchanged, the digest is
    byte-for-byte identical, regardless of who runs the importer or when.
    """
    normalised: list[dict[str, Any]] = []
    for d in sorted(docs, key=lambda x: x["slug"]):
        controls = sorted(d["controls"], key=lambda c: c["control_id"])
        normalised.append({
            "slug": d["slug"],
            "version": d["version"],
            "authority": d.get("authority"),
            "jurisdiction": d.get("jurisdiction"),
            "controls": [
                {
                    "control_id": c["control_id"],
                    "title": c["title"],
                    "description": c.get("description"),
                    "requirement_text": c.get("requirement_text"),
                    "source_ref": c.get("source_ref"),
                    "category": c.get("category"),
                    "is_mandatory": c.get("is_mandatory", True),
                    "applies_to": sorted(c.get("applies_to", [])),
                    "evidence_hints": c.get("evidence_hints", []),
                    "auto_check": c.get("auto_check", {}),
                }
                for c in controls
            ],
        })
    blob = json.dumps(normalised, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_docs(strict: bool = True) -> list[dict[str, Any]]:
    """Load + validate every framework YAML; return docs in slug order.

    Pure helper exposed for tests + the determinism CI check — does NOT touch
    the database.
    """
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    docs: list[dict[str, Any]] = []
    for path in sorted(FRAMEWORKS_DIR.glob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        errs = list(validator.iter_errors(d))
        if errs and strict:
            for e in errs:
                print(f"[SCHEMA] {path}: {'/'.join(str(p) for p in e.path)}: {e.message}", file=sys.stderr)
            raise SystemExit(1)
        docs.append(d)
    return sorted(docs, key=lambda x: x["slug"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    sys.exit(import_all(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
