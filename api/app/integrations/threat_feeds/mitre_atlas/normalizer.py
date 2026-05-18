"""MITRE ATLAS feed normalizer (Phase 7.2).

ATLAS (Adversarial Threat Landscape for AI Systems) publishes a public
JSON catalogue of attack techniques against ML/LLM systems. We pull
the `techniques.json` snapshot, filter for non-deprecated entries,
and map each technique to a DraftThreat with sensible defaults.

Upstream record shape (illustrative):
    {
      "id": "AML.T0051",
      "name": "Indirect Prompt Injection",
      "description": "...",
      "tactics": ["AML.TA0007"],
      "kill_chain_phases": ["initial-access"],
      "version": "1.0",
      "deprecated": false
    }

The normalizer maps:
  - ATLAS technique ID → mitre_atlas_ids[]
  - description → verbatim_description
  - tactic hints + name keywords → AEGIS classes + vectors

Real-mode fetches from https://atlas.mitre.org/techniques.json. In
dev / test mode, the fetcher pulls from a fixture under
catalogue/threats/fixtures/mitre_atlas.json so CI does not depend
on the internet.
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
    / "catalogue" / "threats" / "fixtures" / "mitre_atlas.json"
)
SOURCE_URL = "https://atlas.mitre.org/techniques.json"


# Keyword → (classes, vectors) heuristic. Drives the initial mapping;
# the reviewer is expected to refine before publish.
_NAME_HINTS: dict[str, tuple[list[str], list[str]]] = {
    "prompt injection":   (["direct_prompt_injection"], ["browser_webapp", "cli_sdk"]),
    "indirect prompt":    (["indirect_prompt_injection"], ["browser_webapp", "browser_extension"]),
    "model poison":       (["model_integrity", "supply_chain"], ["local_model", "cloud_ai_control_plane"]),
    "training data":      (["model_integrity"], ["cloud_ai_control_plane"]),
    "model extraction":   (["data_exfiltration"], ["cloud_ai_control_plane", "cli_sdk"]),
    "model inversion":    (["data_exfiltration"], ["cli_sdk"]),
    "evasion":            (["jailbreak"], ["cli_sdk", "cloud_ai_control_plane"]),
    "exfiltrat":          (["data_exfiltration"], ["cli_sdk"]),
    "supply chain":       (["supply_chain"], ["coding_assistant", "local_model"]),
    "denial":             (["cost_availability_abuse"], ["cli_sdk", "cloud_ai_control_plane"]),
    "deepfake":           (["deepfake"], ["browser_webapp"]),
    "discover ml":        (["data_exfiltration", "output_oversharing"], ["browser_extension", "browser_webapp"]),
    "spoof ml":           (["deepfake", "output_oversharing"], ["browser_webapp"]),
}


def _classes_vectors(name: str, description: str) -> tuple[list[str], list[str]]:
    hay = f"{name}\n{description}".lower()
    classes: list[str] = []
    vectors: list[str] = []
    for needle, (c, v) in _NAME_HINTS.items():
        if needle in hay:
            classes.extend(c)
            vectors.extend(v)
    if not classes:
        classes = ["data_exfiltration"]  # safest default; reviewer overrides
    if not vectors:
        vectors = ["cli_sdk"]
    # de-dup while preserving order
    classes = list(dict.fromkeys(classes))
    vectors = list(dict.fromkeys(vectors))
    return classes, vectors


@register(source="mitre_atlas")
class MitreAtlasNormalizer(BaseFeedNormalizer):
    source = "mitre_atlas"
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

        for rec in data.get("techniques", data if isinstance(data, list) else []):
            if not isinstance(rec, dict):
                continue
            if rec.get("deprecated") is True:
                continue
            yield rec

    def normalize(self, raw: dict[str, Any]) -> DraftThreat | None:
        atlas_id = raw.get("id") or ""
        name = raw.get("name") or atlas_id
        desc = raw.get("description") or ""
        if not atlas_id.startswith("AML."):
            return None

        classes, vectors = _classes_vectors(name, desc)
        return DraftThreat(
            # Stable AEGIS-T-A-NNNN where NNNN is the ATLAS technique number.
            threat_id=f"AEGIS-T-ATLAS-{atlas_id.split('.')[-1][1:].zfill(4)}",
            title=name,
            source_ref=f"MITRE ATLAS {atlas_id} (accessed {date.today().isoformat()})",
            verbatim_description=desc,
            severity="high",                    # reviewer-tunable
            classes=classes,
            vectors=vectors,
            mitre_atlas_ids=[atlas_id],
            applies_to_jurisdictions=["global"],
            # Empty exposure_check forces the reviewer to add at least one
            # predicate before publish — the catalogue validator rejects
            # records without one.
            exposure_check={},
            evidence_hints=[
                f"Upstream MITRE ATLAS technique {atlas_id}",
            ],
            catalogue_version="1.0.0",
            last_updated=date.today(),
        )

    def upstream_id_of(self, raw: dict[str, Any]) -> str:
        return str(raw.get("id") or "")
