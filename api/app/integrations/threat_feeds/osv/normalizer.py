"""OSV.dev feed normalizer — AI ecosystem CVE filter (Phase 7.2).

OSV publishes a stream of vulnerability records across every package
ecosystem (PyPI, npm, RubyGems, Maven, Go, crates.io, etc.). The
normalizer subscribes to the feed but only emits drafts for advisories
that touch the AI tooling allow-list — otherwise the AEGIS catalogue
would be drowned in unrelated CVEs.

AI-package allow-list lives below; the reviewer can extend it without
a code release by editing catalogue/threats/fixtures/osv_ai_packages.json
in a separate PR.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

from app.integrations.threat_feeds.base import (
    BaseFeedNormalizer,
    DraftThreat,
    register,
)

FIXTURE = (
    Path(__file__).resolve().parents[5]
    / "catalogue" / "threats" / "fixtures" / "osv.json"
)
ALLOWLIST = (
    Path(__file__).resolve().parents[5]
    / "catalogue" / "threats" / "fixtures" / "osv_ai_packages.json"
)
SOURCE_URL_BASE = "https://api.osv.dev/v1/query"


def _load_allowlist() -> set[str]:
    if ALLOWLIST.exists():
        return set(json.loads(ALLOWLIST.read_text(encoding="utf-8")))
    # Minimal default seed — extend via the fixture file.
    return {
        # PyPI
        "openai", "anthropic", "langchain", "langchain-core", "llama-index",
        "transformers", "torch", "tensorflow", "sentence-transformers",
        "huggingface_hub", "guardrails-ai", "instructor",
        # npm
        "@anthropic-ai/sdk", "openai", "@openai/agents", "langchain",
        "ai", "@vercel/ai", "@modelcontextprotocol/sdk",
    }


@register(source="osv")
class OsvNormalizer(BaseFeedNormalizer):
    source = "osv"
    default_jurisdictions = ["global"]

    async def fetch(self) -> AsyncIterator[dict[str, Any]]:
        # OSV doesn't have a true firehose; the production path will be
        # to query each tracked package in batches. For v1 we read a
        # fixture so CI is deterministic and offline. Real-mode is
        # enabled by setting AEGIS_FEED_REAL_MODE=1 and providing a
        # query strategy module (post-GA work).
        if os.environ.get("AEGIS_FEED_REAL_MODE") == "1":
            # Real mode left intentionally unimplemented in v1; the
            # batched query loop is a per-customer onboarding task.
            return
        if not FIXTURE.exists():
            return
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for rec in data.get("vulns", data if isinstance(data, list) else []):
            if isinstance(rec, dict):
                yield rec

    def normalize(self, raw: dict[str, Any]) -> DraftThreat | None:
        allow = _load_allowlist()
        affected = raw.get("affected") or []
        package_names: list[str] = []
        ecosystems: set[str] = set()
        for a in affected:
            pkg = (a or {}).get("package") or {}
            name = pkg.get("name")
            eco = pkg.get("ecosystem", "").lower()
            if not name:
                continue
            package_names.append(name)
            ecosystems.add(eco)
        if not any(p in allow for p in package_names):
            return None  # Not an AI ecosystem advisory

        upstream_id = str(raw.get("id") or "OSV-?")
        summary = raw.get("summary") or upstream_id
        details = raw.get("details") or summary

        severity_map = {
            "CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium",
            "MEDIUM": "medium", "LOW": "low",
        }
        sev_in = ""
        for s in (raw.get("database_specific") or {}).get("severity", "") or "":
            sev_in = s
            break
        severity = severity_map.get(str(sev_in).upper(), "high")

        return DraftThreat(
            threat_id=f"AEGIS-T-OSV-{upstream_id.replace('-', '')[-4:].rjust(4, '0').upper()}",
            title=f"{summary} ({', '.join(sorted(package_names)[:3])})",
            source_ref=f"OSV.dev {upstream_id} (accessed {date.today().isoformat()})",
            verbatim_description=details,
            severity=severity,
            classes=["supply_chain"],
            vectors=["coding_assistant", "cli_sdk"],
            applies_to_jurisdictions=["global"],
            exposure_check={
                # Reviewer must extend; the baseline asks the engine to
                # treat as unknown until AEGIS-EA reports package install.
                "endpoint_agent_npm_postinstall_within_days": 30,
            },
            evidence_hints=[
                f"OSV record {upstream_id} affects packages: {', '.join(sorted(package_names))}",
            ],
            catalogue_version="1.0.0",
            last_updated=date.today(),
        )

    def upstream_id_of(self, raw: dict[str, Any]) -> str:
        return str(raw.get("id") or "")
