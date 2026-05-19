"""Auto-seed the AI service catalogue, compliance frameworks and threat
catalogue when their tables are empty.

This is the single biggest "huh, why is everything blank?" cause:

  * `ai_services` empty             -> network/XDR matcher has no patterns
                                       -> shadow registration never fires
                                       -> AI Registry never populates
  * `threats` empty                 -> /threats page blank, exposure
                                       engine has nothing to evaluate
  * `compliance_frameworks` empty   -> /compliance dashboard blank

The platform previously assumed an operator would run `make
catalogue-import`, `make framework-import`, `make threats-import` after
first install. That's a real footgun: stand up the stack via
docker-compose, send some traffic, see no detection, and conclude AEGIS
is broken. This module closes the gap by running each importer
automatically the first time the API process sees an empty table.

Idempotent + safe:
  * Re-importing an already-populated table is a no-op (the importers
    are idempotent upserts already).
  * To force a reseed when the YAML files have changed, call the admin
    POST /v1/admin/reseed endpoint — it bypasses the empty-table guard.
  * Failures are LOGGED, NOT RAISED — a missing fixtures directory or
    a DB hiccup must never block API startup.

Determinism contract held: the threats importer's
.inventory_digest fixture check still runs, so a deployment with a
drifted catalogue refuses to import threats and surfaces the drift
through the structured log.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# Repository layout: the API container mounts /workspace/catalogue
# (compose) OR the repo's catalogue/ when running locally. Resolve at
# call time so test fixtures + production both work.
def _catalogue_root() -> Path:
    for candidate in (
        Path(os.environ.get("AEGIS_CATALOGUE_DIR", "")),
        Path("/workspace/catalogue"),
        Path(__file__).resolve().parents[3] / "catalogue",
    ):
        if candidate and candidate.exists():
            return candidate
    return Path("catalogue")


async def _count_rows(session, table_sql: str) -> int:
    from sqlalchemy import text
    row = (await session.execute(text(f"SELECT COUNT(*)::int AS n FROM {table_sql}"))).first()
    return int(row[0]) if row else 0


def _run_importer(script_path: Path, label: str) -> dict[str, Any]:
    """Subprocess the existing importer scripts so we don't have to
    duplicate their YAML schema + upsert logic here.

    Returns {ok, stdout_tail, stderr_tail, returncode}.
    """
    if not script_path.exists():
        log.warning("aegis.seed.importer_missing",
                    extra={"label": label, "path": str(script_path)})
        return {"ok": False, "error": f"importer not found: {script_path}"}
    try:
        # The importers expect to be run from the repo root so their
        # path resolution + sys.path manipulation works.
        result = subprocess.run(
            [sys.executable, str(script_path), "-v"],
            cwd=script_path.parents[1].parent,    # repo root
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        if not ok:
            log.warning(
                "aegis.seed.importer_failed",
                extra={
                    "label": label,
                    "returncode": result.returncode,
                    "stderr_tail": result.stderr[-600:] if result.stderr else "",
                },
            )
        else:
            log.info(
                "aegis.seed.importer_ok",
                extra={
                    "label": label,
                    "stdout_tail": result.stdout[-400:] if result.stdout else "",
                },
            )
        return {
            "ok": ok,
            "label": label,
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "")[-2000:],
            "stderr_tail": (result.stderr or "")[-2000:],
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("aegis.seed.importer_exception",
                      extra={"label": label})
        return {"ok": False, "label": label, "error": str(exc)}


async def auto_seed_if_empty() -> dict[str, Any]:
    """Run on API startup. Imports each catalogue only when its table
    is empty. Safe to call multiple times.
    """
    from app.core.database import SessionLocal

    catalogue_root = _catalogue_root()
    results: dict[str, Any] = {"catalogue_root": str(catalogue_root)}

    async with SessionLocal() as session:
        try:
            counts = {
                "ai_services":           await _count_rows(session, "ai_services"),
                "threats":               await _count_rows(session, "threats"),
                "compliance_frameworks": await _count_rows(session, "compliance_frameworks"),
            }
        except Exception as exc:  # noqa: BLE001  — DB may not be migrated yet
            log.warning("aegis.seed.count_failed", error=str(exc))
            return {"ok": False, "error": "could not query seed tables (DB not migrated yet?)"}

    results["before"] = counts

    # AI service catalogue
    if counts["ai_services"] == 0:
        results["ai_services"] = _run_importer(
            catalogue_root / "scripts" / "importer.py", "ai_services",
        )
    else:
        results["ai_services"] = {"skipped": True, "reason": f"table has {counts['ai_services']} rows"}

    # Threats
    if counts["threats"] == 0:
        results["threats"] = _run_importer(
            catalogue_root / "scripts" / "threats_importer.py", "threats",
        )
    else:
        results["threats"] = {"skipped": True, "reason": f"table has {counts['threats']} rows"}

    # Compliance frameworks
    if counts["compliance_frameworks"] == 0:
        results["compliance_frameworks"] = _run_importer(
            catalogue_root / "scripts" / "import_frameworks.py", "compliance_frameworks",
        )
    else:
        results["compliance_frameworks"] = {
            "skipped": True, "reason": f"table has {counts['compliance_frameworks']} rows",
        }

    return results


async def force_reseed() -> dict[str, Any]:
    """Admin trigger: run all three importers regardless of current
    table state. Used after editing the YAML files to push changes
    through without a container restart."""
    catalogue_root = _catalogue_root()
    return {
        "catalogue_root":        str(catalogue_root),
        "ai_services":           _run_importer(catalogue_root / "scripts" / "importer.py",           "ai_services"),
        "threats":               _run_importer(catalogue_root / "scripts" / "threats_importer.py",   "threats"),
        "compliance_frameworks": _run_importer(catalogue_root / "scripts" / "import_frameworks.py", "compliance_frameworks"),
    }


async def seed_status() -> dict[str, Any]:
    """Read-only health snapshot of every seed table. Used by the
    Dashboard banner so operators can see the state at a glance."""
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        try:
            counts = {
                "ai_services":           await _count_rows(session, "ai_services"),
                "threats":               await _count_rows(session, "threats"),
                "compliance_frameworks": await _count_rows(session, "compliance_frameworks"),
                "compliance_controls":   await _count_rows(session, "compliance_controls"),
                "ai_systems":            await _count_rows(session, "ai_systems"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    healthy = (
        counts["ai_services"] > 0
        and counts["threats"] > 0
        and counts["compliance_frameworks"] > 0
    )
    advice: list[str] = []
    if counts["ai_services"] == 0:
        advice.append(
            "Run POST /v1/admin/reseed OR `make catalogue-import` — without "
            "ai_services patterns, the matcher cannot identify AI traffic and "
            "the Registry stays empty even when ingest is firing."
        )
    if counts["threats"] == 0:
        advice.append(
            "Run POST /v1/admin/reseed OR `make threats-import` — without "
            "threats the /threats page is blank and exposure engine has "
            "nothing to evaluate."
        )
    if counts["compliance_frameworks"] == 0:
        advice.append(
            "Run POST /v1/admin/reseed OR `make framework-import` — without "
            "frameworks the /compliance dashboard is blank."
        )

    return {
        "ok":      healthy,
        "counts":  counts,
        "advice":  advice,
    }
