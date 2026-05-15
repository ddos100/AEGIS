"""Import compliance framework YAML files into ai_frameworks + ai_controls.

Same invocation patterns as :mod:`catalogue.scripts.importer` —
runs from inside the api container OR from the repo root on the host.

  docker compose exec api python /workspace/catalogue/scripts/import_frameworks.py -v

Idempotent: upserts by (framework_slug) and (framework_id, control_id).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

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

from app.models.compliance_control import ComplianceControl  # noqa: E402
from app.models.compliance_framework import ComplianceFramework  # noqa: E402


def _connect() -> Session:
    url = os.environ.get("DATABASE_URL_SYNC", "postgresql+psycopg2://aegis:aegis@postgres:5432/aegis")
    return Session(create_engine(url, future=True), future=True)


def import_all(*, dry_run: bool = False, verbose: bool = False) -> int:
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
                    category=ctrl.get("category"),
                    is_mandatory=ctrl.get("is_mandatory", True),
                    applies_to=ctrl.get("applies_to", []),
                    evidence_hints=ctrl.get("evidence_hints", []),
                    auto_check=ctrl.get("auto_check", {}),
                )
                .on_conflict_do_update(
                    constraint="uq_controls_control_id",
                    set_={
                        "title":          ctrl["title"],
                        "description":    ctrl.get("description"),
                        "category":       ctrl.get("category"),
                        "is_mandatory":   ctrl.get("is_mandatory", True),
                        "applies_to":     ctrl.get("applies_to", []),
                        "evidence_hints": ctrl.get("evidence_hints", []),
                        "auto_check":     ctrl.get("auto_check", {}),
                    },
                )
            )
            session.execute(cstmt)
            ctrl_total += 1
            if verbose:
                print(f"  {d['slug']:>22}  {ctrl['control_id']}")

    session.commit()
    print(f"Frameworks: {fw_created} created / {fw_updated} updated. Controls: {ctrl_total}.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    sys.exit(import_all(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
