"""Thin Claude API wrapper for risk narratives + AISIA drafts.

Why hand-rolled rather than the Anthropic SDK:
  - We need fine control over prompt caching, max_tokens, and (eventually)
    structured outputs. The SDK is fine but the surface here is small enough
    that the dependency saving is worth it.
  - Easier to mock from the test suite without monkeypatching boto-style
    factories.

If ``settings.anthropic_api_key`` isn't set, every call returns ``None`` —
the calling code falls back to a stock narrative. That keeps dev/test
deployments offline-friendly.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import log

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# System prompt is cached by Anthropic when we send the same string repeatedly
# (we use a cache_control breakpoint). The body is intentionally compact —
# we trust the model to follow the structure given the explicit headings.
RISK_NARRATIVE_SYSTEM = """You are AEGIS, an AI risk assessment specialist embedded in an enterprise governance platform serving Indian regulated-sector enterprises (BFSI, insurance, fintech, OTT).

Given an AI system's risk scores, intended purpose, data classification, and \
regulatory flags, produce a 200–300 word risk narrative with these sections:

  1. Risk drivers — which of the five dimensions (data sensitivity, AI capability, regulatory exposure, access scope, provider trust) drove the score, and the specific evidence.
  2. Recommended controls — top three actionable controls aligned to ISO 42001 Annex A. Cite the control reference (e.g. "ISO 42001 A.4.3").
  3. Regulatory considerations — any RBI / IRDAI / SEBI / DPDPA / EU AI Act flags that apply, and what evidence will be required for audit.

Be specific, terse, and avoid generic boilerplate. Reference the system's actual characteristics. Do not include disclaimers."""

AISIA_DRAFT_SYSTEM = """You are AEGIS. The operator is preparing an AI System Impact Assessment under ISO 42001 Clause 6.1.2 for a specific system. Produce a concise draft (250–400 words) covering these six dimensions in order, with one paragraph each:

  1. Intended purpose & legitimate basis
  2. Affected population
  3. Severity of potential harm
  4. Reversibility
  5. Human oversight design
  6. Recommended treatment decision (accept-with-controls / restrict / block)

The operator will edit the draft. Be explicit about uncertainty — if a dimension cannot be assessed from the supplied context, say so plainly."""


class ClaudeUnavailable(RuntimeError):
    """Raised when the API key isn't configured. Callers should fall back."""


async def _post(model: str, system: str, user: str, *, max_tokens: int) -> dict[str, Any]:
    if not settings.anthropic_api_key:
        raise ClaudeUnavailable("anthropic_api_key not configured")
    headers = {
        "anthropic-version": ANTHROPIC_VERSION,
        "x-api-key":         settings.anthropic_api_key,
        "content-type":      "application/json",
    }
    body = {
        "model":      model,
        "max_tokens": max_tokens,
        # Prompt-cache the system block — it doesn't change per call.
        "system":     [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages":   [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(ANTHROPIC_API, headers=headers, json=body)
        r.raise_for_status()
        return r.json()


def _extract_text(resp: dict[str, Any]) -> str:
    parts = resp.get("content") or []
    return "\n".join(b.get("text", "") for b in parts if b.get("type") == "text").strip()


async def generate_risk_narrative(system: dict[str, Any], scores: dict[str, Any]) -> str | None:
    """Return the narrative text or None if Claude isn't available / fails."""
    try:
        user = (
            f"AI System: {system.get('name')}\n"
            f"Category: {system.get('category')} / {system.get('subcategory')}\n"
            f"Intended Purpose: {system.get('intended_purpose') or '(not documented)'}\n"
            f"Data Types: {', '.join(system.get('data_types_processed') or [])}\n"
            f"Affected Subjects: {', '.join(system.get('affected_data_subjects') or [])}\n"
            f"EU AI Act Category: {system.get('eu_ai_act_category')}\n"
            f"Geographic Scope: {', '.join(system.get('geographic_scope') or [])}\n"
            f"\n"
            f"Risk dimension scores (0–100):\n"
            f"  data_sensitivity:    {scores['data_sensitivity']}\n"
            f"  ai_capability:       {scores['ai_capability']}\n"
            f"  regulatory_exposure: {scores['regulatory_exposure']}\n"
            f"  access_scope:        {scores['access_scope']}\n"
            f"  provider_trust:      {scores['provider_trust']}\n"
            f"  TOTAL:               {scores['total']}  ({scores['risk_level']})\n"
        )
        resp = await asyncio.wait_for(
            _post(settings.claude_model_default, RISK_NARRATIVE_SYSTEM, user, max_tokens=600),
            timeout=20.0,
        )
        return _extract_text(resp)
    except ClaudeUnavailable:
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.claude.risk_narrative_failed", error=str(exc))
        return None


async def generate_aisia_draft(system: dict[str, Any]) -> str | None:
    try:
        user = (
            f"System: {system.get('name')}\n"
            f"Category: {system.get('category')}\n"
            f"Intended purpose: {system.get('intended_purpose') or '(not documented)'}\n"
            f"Output type: {system.get('output_type')}\n"
            f"Data types: {', '.join(system.get('data_types_processed') or [])}\n"
            f"Affected subjects: {', '.join(system.get('affected_data_subjects') or [])}\n"
            f"User population: {system.get('user_population')}\n"
            f"Existing human oversight: {system.get('human_oversight_desc') or '(none documented)'}\n"
            f"Risk level: {system.get('risk_level')} ({system.get('current_risk_score')})\n"
        )
        resp = await asyncio.wait_for(
            _post(settings.claude_model_default, AISIA_DRAFT_SYSTEM, user, max_tokens=1000),
            timeout=30.0,
        )
        return _extract_text(resp)
    except ClaudeUnavailable:
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.claude.aisia_draft_failed", error=str(exc))
        return None
