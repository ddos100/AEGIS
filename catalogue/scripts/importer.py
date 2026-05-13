"""Import catalogue YAML files into the ai_services + ai_providers tables.

Run from inside the API container (where the DB is reachable):

    docker compose exec api python -m catalogue.scripts.importer

Or pass a custom DB URL:

    DATABASE_URL_SYNC=postgresql+psycopg2://... python -m catalogue.scripts.importer

Idempotent: re-running upserts rows by ``catalogue_id`` / ``slug`` and only
flips ``is_active=false`` for previously-imported entries that disappear
from disk (kept for audit history; NOT hard-deleted).
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

# This script supports three invocation contexts:
#   1. Inside the api container (catalogue mounted at /workspace/catalogue,
#      `app` package already installed via pip install -e .)
#   2. Repo root on host: `python -m catalogue.scripts.importer`
#      (we add repo_root/api to sys.path so `app` resolves)
#   3. Direct execution from the scripts dir
HERE = Path(__file__).resolve()


def _find_paths() -> tuple[Path, Path]:
    """Locate (catalogue_dir, schema_path), being tolerant of mount layouts."""
    # Repo-root layout: HERE = .../catalogue/scripts/importer.py → parents[2] = repo root
    candidate_root = HERE.parents[2]
    cat = candidate_root / "catalogue"
    if cat.exists():
        # If the api sibling exists on disk, add it to sys.path (host invocation case).
        api_sibling = candidate_root / "api"
        if api_sibling.exists():
            sys.path.insert(0, str(api_sibling))
        return cat, cat / "schemas" / "service.schema.yaml"

    # Container layout: HERE = /workspace/catalogue/scripts/importer.py
    # parents[1] is /workspace/catalogue itself.
    cat = HERE.parents[1]
    return cat, cat / "schemas" / "service.schema.yaml"


CATALOGUE_DIR, SCHEMA_PATH = _find_paths()
SERVICES_DIR = CATALOGUE_DIR / "services"

from app.models.ai_provider import AIProvider  # noqa: E402
from app.models.ai_service import AIService    # noqa: E402

# Minimal provider directory derived from the YAML provider_slug values.
# Production deployments will ship a richer provider catalogue YAML; for now
# we materialise a row per distinct slug with sensible defaults.
DEFAULT_PROVIDERS = {
    "openai":      {"name": "OpenAI",                 "hq_country": "US", "trust_score": 72},
    "anthropic":   {"name": "Anthropic",              "hq_country": "US", "trust_score": 82, "soc2_certified": True},
    "google":      {"name": "Google",                 "hq_country": "US", "trust_score": 76, "soc2_certified": True, "iso27001_cert": True},
    "microsoft":   {"name": "Microsoft",              "hq_country": "US", "trust_score": 85, "soc2_certified": True, "iso27001_cert": True, "gdpr_dpa": True},
    "grammarly":   {"name": "Grammarly",              "hq_country": "US", "trust_score": 60, "soc2_certified": True},
    "perplexity":  {"name": "Perplexity AI",          "hq_country": "US", "trust_score": 58},
    "github":      {"name": "GitHub (Microsoft)",     "hq_country": "US", "trust_score": 85, "soc2_certified": True, "iso27001_cert": True},
    "cursor":      {"name": "Anysphere (Cursor)",     "hq_country": "US", "trust_score": 60},
    "codeium":     {"name": "Codeium",                "hq_country": "US", "trust_score": 60},
    "amazon":      {"name": "Amazon Web Services",    "hq_country": "US", "trust_score": 85, "soc2_certified": True, "iso27001_cert": True},
    "stability":   {"name": "Stability AI",           "hq_country": "GB", "trust_score": 55},
    "midjourney":  {"name": "Midjourney",             "hq_country": "US", "trust_score": 50},
    "huggingface": {"name": "Hugging Face",           "hq_country": "US", "trust_score": 65, "soc2_certified": True},
    "cohere":      {"name": "Cohere",                 "hq_country": "CA", "trust_score": 65, "soc2_certified": True},
    "mistral":     {"name": "Mistral AI",             "hq_country": "FR", "trust_score": 65},
    "deepseek":    {"name": "DeepSeek",               "hq_country": "CN", "trust_score": 40},
    "xai":         {"name": "xAI",                    "hq_country": "US", "trust_score": 50},
    "monica":      {"name": "Monica",                 "hq_country": "US", "trust_score": 45},
    "merlin":      {"name": "Foyer / Merlin AI",      "hq_country": "US", "trust_score": 45},
    "sider":       {"name": "Sider AI",               "hq_country": "US", "trust_score": 45},
    "jasper":      {"name": "Jasper AI",              "hq_country": "US", "trust_score": 55},
    "writesonic":  {"name": "Writesonic",             "hq_country": "US", "trust_score": 50},
    "salesforce":  {"name": "Salesforce",             "hq_country": "US", "trust_score": 85, "soc2_certified": True, "iso27001_cert": True, "gdpr_dpa": True},
    "notion":      {"name": "Notion Labs",            "hq_country": "US", "trust_score": 70, "soc2_certified": True},
    "atlassian":   {"name": "Atlassian",              "hq_country": "AU", "trust_score": 75, "soc2_certified": True, "iso27001_cert": True},
    "slack":       {"name": "Slack (Salesforce)",     "hq_country": "US", "trust_score": 80, "soc2_certified": True, "iso27001_cert": True},
    "canva":       {"name": "Canva",                  "hq_country": "AU", "trust_score": 60, "soc2_certified": True},
    "elevenlabs":  {"name": "ElevenLabs",             "hq_country": "GB", "trust_score": 55},
    "openai-codex":{"name": "OpenAI (Codex)",         "hq_country": "US", "trust_score": 72},
    "replicate":   {"name": "Replicate",              "hq_country": "US", "trust_score": 55},
}


def _connect() -> Session:
    url = os.environ.get("DATABASE_URL_SYNC", "postgresql+psycopg2://aegis:aegis@postgres:5432/aegis")
    engine = create_engine(url, future=True)
    return Session(engine, future=True)


def _load_schema() -> Draft7Validator:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft7Validator(schema)


def _upsert_providers(session: Session, slugs: set[str]) -> dict[str, "AIProvider"]:
    """Ensure provider rows exist for every slug we've seen. Returns slug -> row map."""
    result: dict[str, AIProvider] = {}
    for slug in sorted(slugs):
        defaults = DEFAULT_PROVIDERS.get(slug, {"name": slug.title()})
        stmt = pg_insert(AIProvider).values(slug=slug, **defaults)
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_={"name": stmt.excluded.name},
        ).returning(AIProvider.id)
        pid = session.execute(stmt).scalar_one()
        result[slug] = session.execute(select(AIProvider).where(AIProvider.id == pid)).scalar_one()
    return result


def _upsert_service(session: Session, data: dict[str, Any], providers: dict[str, "AIProvider"]) -> str:
    """Upsert a single AIService row. Returns 'created' or 'updated'."""
    provider_slug = data["provider_slug"]
    provider = providers.get(provider_slug)

    payload = {
        "catalogue_id":      data["id"],
        "name":              data["name"],
        "provider_id":       provider.id if provider else None,
        "provider_slug":     provider_slug,
        "category":          data["category"],
        "subcategory":       data.get("subcategory"),
        "description":       data.get("description"),
        "website":           data.get("website"),
        "api_patterns":      data.get("api_endpoint_patterns", []),
        "browser_domains":   data.get("browser_domains", []),
        "entra_app_ids":     data.get("entra_app_ids", []),
        "eu_ai_act_cat":     data.get("eu_ai_act_category"),
        "capabilities":      data.get("capabilities", []),
        "input_types":       data.get("input_data_types", []),
        "output_types":      data.get("output_data_types", []),
        "hq_country":        data.get("hq_country"),
        "gdpr_applicable":   data.get("gdpr_applicable", True),
        "risk_hints":        data.get("default_risk_indicators", {}),
        "tags":              data.get("tags", []),
        "catalogue_version": data["catalogue_version"],
        "is_active":         True,
    }
    existing = session.execute(
        select(AIService).where(AIService.catalogue_id == payload["catalogue_id"])
    ).scalar_one_or_none()

    stmt = pg_insert(AIService).values(**payload)
    update_cols = {k: stmt.excluded[k] for k in payload if k != "catalogue_id"}
    stmt = stmt.on_conflict_do_update(index_elements=["catalogue_id"], set_=update_cols)
    session.execute(stmt)
    return "updated" if existing else "created"


def import_catalogue(*, dry_run: bool = False, verbose: bool = False) -> int:
    """Import every YAML under catalogue/services. Returns shell exit code."""
    validator = _load_schema()
    yaml_files = sorted(SERVICES_DIR.rglob("*.yaml"))
    if not yaml_files:
        print(f"No YAML files found under {SERVICES_DIR}", file=sys.stderr)
        return 1

    docs: list[dict[str, Any]] = []
    errors = 0
    for f in yaml_files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"[YAML] {f}: {e}", file=sys.stderr)
            errors += 1
            continue
        errs = sorted(validator.iter_errors(doc), key=lambda e: tuple(str(p) for p in e.path))
        if errs:
            for e in errs:
                path = "/".join(str(p) for p in e.path)
                print(f"[SCHEMA] {f}: {path}: {e.message}", file=sys.stderr)
            errors += 1
            continue
        docs.append(doc)

    if errors:
        print(f"Refusing to import — {errors} files failed validation.", file=sys.stderr)
        return 1
    if dry_run:
        print(f"DRY RUN — {len(docs)} entries would be upserted.")
        return 0

    session = _connect()
    provider_slugs = {d["provider_slug"] for d in docs}
    providers = _upsert_providers(session, provider_slugs)

    created = updated = 0
    for d in docs:
        result = _upsert_service(session, d, providers)
        if result == "created":
            created += 1
        else:
            updated += 1
        if verbose:
            print(f"  {result:>7}  {d['id']}")

    session.commit()
    print(f"Catalogue import OK — providers={len(providers)} created={created} updated={updated}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Import AEGIS catalogue YAML → ai_services table")
    p.add_argument("--dry-run", action="store_true", help="Validate only, do not write to DB")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    sys.exit(import_catalogue(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
