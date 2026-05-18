"""Import threat YAML files into the `threats` table.

Same invocation patterns as :mod:`catalogue.scripts.import_frameworks`.
Runs from inside the api container OR from the repo root on the host.

  docker compose exec api python /workspace/catalogue/scripts/threats_importer.py -v

Determinism guarantees
----------------------
- Files are sorted alphabetically (relative path) before processing.
- Upserts keyed by `threat_id` (unique). Repeat runs are byte-for-byte
  identical at the DB level.
- Before any DB writes, the script verifies the live catalogue digest
  against the pinned `.inventory_digest` fixture (unless --no-digest-check
  is passed). This guarantees the imported catalogue matches the commit
  the operator believes they are deploying.
- No LLM is on the import path — all text is verbatim from the YAML
  files committed to git.

Idempotent: re-running produces no DB diff if the catalogue is unchanged.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator

HERE = Path(__file__).resolve().parent


def _find_paths() -> tuple[Path, Path]:
    root = HERE.parents[2]
    cat = root / "catalogue"
    if cat.exists():
        api_sibling = root / "api"
        if api_sibling.exists():
            sys.path.insert(0, str(api_sibling))
        return cat, cat / "threats" / "schema.yaml"
    cat = HERE.parents[1]
    return cat, cat / "threats" / "schema.yaml"


CATALOGUE_DIR, SCHEMA_PATH = _find_paths()
THREATS_DIR = CATALOGUE_DIR / "threats"
DIGEST_PATH = THREATS_DIR / ".inventory_digest"


def _connect():  # noqa: ANN202
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    url = os.environ.get("DATABASE_URL_SYNC",
                          "postgresql+psycopg2://aegis:aegis@postgres:5432/aegis")
    return Session(create_engine(url, future=True), future=True)


def load_docs(strict: bool = True) -> list[dict[str, Any]]:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    docs: list[dict[str, Any]] = []
    errors = 0
    for path in sorted(p for p in THREATS_DIR.rglob("*.yaml") if p.name != "schema.yaml"):
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"[YAML] {path}: {exc}", file=sys.stderr)
            errors += 1
            continue
        for err in sorted(validator.iter_errors(d),
                           key=lambda e: tuple(str(p) for p in e.path)):
            print(f"[SCHEMA] {path}: {'/'.join(str(p) for p in err.path)}: {err.message}",
                  file=sys.stderr)
            errors += 1
        else:
            docs.append(d)
    if strict and errors:
        raise SystemExit(f"Refusing to import — {errors} files failed validation.")
    return sorted(docs, key=lambda d: d["threat_id"])


def inventory_digest(docs: list[dict[str, Any]]) -> str:
    """Same canonical encoding as catalogue/scripts/threats_digest.py.
    Keep in sync — both must produce the identical hash for the same docs.
    """
    import hashlib
    import json
    canonical = json.dumps(docs, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def import_all(*, dry_run: bool = False, verbose: bool = False,
                skip_digest_check: bool = False) -> int:
    docs = load_docs(strict=True)

    if not skip_digest_check:
        if DIGEST_PATH.exists():
            pinned = DIGEST_PATH.read_text(encoding="utf-8").strip()
            live = inventory_digest(docs)
            if pinned != live:
                print(f"DIGEST DRIFT: pinned={pinned} live={live}", file=sys.stderr)
                print("Refusing to import — re-pin via "
                      "`python catalogue/scripts/threats_digest.py --update` "
                      "if the change was intentional.", file=sys.stderr)
                return 1
        else:
            print("WARN: .inventory_digest missing — skipping drift check",
                  file=sys.stderr)

    if dry_run:
        print(f"DRY RUN — {len(docs)} threats would be upserted.")
        return 0

    # DB-touching imports lazy
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.threat import Threat

    session = _connect()
    created = updated = 0
    try:
        for d in docs:
            stmt = (
                pg_insert(Threat)
                .values(
                    threat_id=d["threat_id"],
                    title=d["title"],
                    source_ref=d["source_ref"],
                    verbatim_description=d["verbatim_description"],
                    description=d.get("description"),
                    severity=d["severity"],
                    classes=d["classes"],
                    vectors=d["vectors"],
                    mitre_atlas_ids=d.get("mitre_atlas_ids") or [],
                    owasp_llm_ids=d.get("owasp_llm_ids") or [],
                    sector_amplifiers=d.get("sector_amplifiers") or [],
                    applies_to_jurisdictions=d.get("applies_to_jurisdictions") or [],
                    exposure_check=d["exposure_check"],
                    mitigation=d.get("mitigation"),
                    evidence_hints=d.get("evidence_hints") or [],
                    compliance_implications=d.get("compliance_implications") or [],
                    catalogue_version=d["catalogue_version"],
                    last_updated=d["last_updated"],
                )
                .on_conflict_do_update(
                    index_elements=["threat_id"],
                    set_={
                        "title":                d["title"],
                        "source_ref":           d["source_ref"],
                        "verbatim_description": d["verbatim_description"],
                        "description":          d.get("description"),
                        "severity":             d["severity"],
                        "classes":              d["classes"],
                        "vectors":              d["vectors"],
                        "mitre_atlas_ids":      d.get("mitre_atlas_ids") or [],
                        "owasp_llm_ids":        d.get("owasp_llm_ids") or [],
                        "sector_amplifiers":    d.get("sector_amplifiers") or [],
                        "applies_to_jurisdictions": d.get("applies_to_jurisdictions") or [],
                        "exposure_check":       d["exposure_check"],
                        "mitigation":           d.get("mitigation"),
                        "evidence_hints":       d.get("evidence_hints") or [],
                        "compliance_implications": d.get("compliance_implications") or [],
                        "catalogue_version":    d["catalogue_version"],
                        "last_updated":         d["last_updated"],
                    },
                )
            )
            session.execute(stmt)
            updated += 1
            if verbose:
                print(f"  upsert {d['threat_id']}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"Imported {len(docs)} threats (upserts: {updated}).")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--no-digest-check", action="store_true",
                   help="Skip the pinned-vs-live inventory digest check.")
    args = p.parse_args()
    rc = import_all(dry_run=args.dry_run, verbose=args.verbose,
                     skip_digest_check=args.no_digest_check)
    sys.exit(rc)


if __name__ == "__main__":
    main()
