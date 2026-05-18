"""AI Incident Database (AIID) feed normalizer — Phase 7.2.

AIID (https://incidentdatabase.ai) curates real-world AI incidents
with structured taxonomies. We pull recent incidents and emit
DraftThreats for ones tagged with classifications we consider
in-scope for AEGIS (data leak, deepfake, jailbreak, model integrity,
autonomous-agent harm).

Privacy: AIID records may include real-world victim identifiers in
prose. The normalizer keeps only the structured fields + the title;
prose body is recorded in the raw_threat_feed payload but the draft
the reviewer sees is bounded to the structured summary.

Fixture path: catalogue/threats/fixtures/aiid.json
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
    / "catalogue" / "threats" / "fixtures" / "aiid.json"
)
SOURCE_URL = "https://incidentdatabase.ai/api/incidents"


_TAXONOMY_TO_CLASSES: dict[str, list[str]] = {
    "data leak":          ["data_exfiltration"],
    "data exposure":      ["data_exfiltration", "output_oversharing"],
    "deepfake":           ["deepfake"],
    "voice clone":        ["deepfake"],
    "jailbreak":          ["jailbreak"],
    "model poisoning":    ["model_integrity", "supply_chain"],
    "model extraction":   ["data_exfiltration"],
    "autonomous":         ["autonomous_agent_loop_out"],
    "agent harm":         ["autonomous_agent_loop_out"],
    "supply chain":       ["supply_chain"],
    "prompt injection":   ["indirect_prompt_injection"],
}


@register(source="aiid")
class AiidNormalizer(BaseFeedNormalizer):
    source = "aiid"
    default_jurisdictions = ["global"]

    async def fetch(self) -> AsyncIterator[dict[str, Any]]:
        if os.environ.get("AEGIS_FEED_REAL_MODE") == "1":
            import httpx
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(SOURCE_URL)
                resp.raise_for_status()
                data = resp.json()
        else:
            if not FIXTURE.exists():
                return
            data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for rec in data.get("incidents", data if isinstance(data, list) else []):
            if isinstance(rec, dict):
                yield rec

    def normalize(self, raw: dict[str, Any]) -> DraftThreat | None:
        incident_id = raw.get("incident_id") or raw.get("id")
        if incident_id is None:
            return None
        title = (raw.get("title") or f"AIID incident {incident_id}").strip()
        summary = (raw.get("description") or raw.get("summary") or "").strip()

        tags = [t.lower() for t in (raw.get("tags") or [])]
        text_hay = (title + "\n" + summary).lower() + "\n" + "\n".join(tags)

        classes: list[str] = []
        for needle, cls in _TAXONOMY_TO_CLASSES.items():
            if needle in text_hay:
                classes.extend(cls)
        if not classes:
            classes = ["output_oversharing"]  # defensive default
        classes = list(dict.fromkeys(classes))

        # AIID incidents are observational; map to "browser_webapp"
        # unless tags suggest otherwise. Reviewer refines.
        vectors = ["browser_webapp"]
        if "agent" in text_hay or "autonomous" in text_hay:
            vectors = ["mcp_agent", "coding_assistant"]
        if "voice" in text_hay or "deepfake" in text_hay:
            vectors = ["browser_webapp", "desktop_client"]

        return DraftThreat(
            threat_id=f"AEGIS-T-AIID-{str(incident_id).zfill(4)}",
            title=title[:180],
            source_ref=f"AI Incident Database #{incident_id} "
                        f"(accessed {date.today().isoformat()})",
            verbatim_description=summary or title,
            severity="medium",   # reviewer adjusts after triage
            classes=classes,
            vectors=vectors,
            applies_to_jurisdictions=["global"],
            exposure_check={},   # must be filled before publish
            evidence_hints=[
                f"Upstream AIID incident #{incident_id}",
            ],
            catalogue_version="1.0.0",
            last_updated=date.today(),
        )

    def upstream_id_of(self, raw: dict[str, Any]) -> str:
        return str(raw.get("incident_id") or raw.get("id") or "")
