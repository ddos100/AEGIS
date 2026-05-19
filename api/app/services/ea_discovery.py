"""Map AEGIS Endpoint Agent events into AI System Registry rows.

Without this bridge, EA events land in `endpoint_agent_events` and stay
there — the Registry, Exposures, and Mitigations panels stay empty
because nothing triggers a catalogue match. This module is the missing
link: it inspects every EA event the ingest endpoint accepts and, when
the event is a discovery-class one, either creates a new
`is_shadow=True` AISystem row or bumps the `last_seen_at` on an
existing one.

Discovery-class EA events and their catalogue lookup strategy:

  ai_provider_connection      payload.provider_domain  -> match against
                                                          ai_services.browser_domains
                                                          OR api_endpoint_patterns
  ai_process_running          payload.process_name     -> match against
                                                          ai_services.id /
                                                          ai_services.name
                                                          (lowercase substring)

Privacy: this module only consumes the structured payload fields the
backend's allow-list already permits. No new field is read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.ai_service import AIService
from app.models.ai_system import AISystem


_DISCOVERY_KINDS = {"ai_provider_connection", "ai_process_running"}


async def auto_register_from_ea_event(
    *,
    session,
    tenant_id: UUID,
    kind: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> dict[str, Any] | None:
    """Inspect one EA event; if it's discovery-class, upsert a shadow
    AISystem and return a WS-broadcast payload (the caller publishes
    AFTER session commit). Returns None for non-discovery events.
    """
    if kind not in _DISCOVERY_KINDS:
        return None

    catalogue = await _resolve_catalogue(session, kind, payload)
    if catalogue is None:
        return None  # no catalogue match — nothing to register

    # Already in the Registry? Update last_seen and (if it's still
    # marked shadow) keep it shadow; bump discovery_sources.
    existing = (await session.execute(
        select(AISystem).where(
            (AISystem.tenant_id == tenant_id) &
            (AISystem.catalogue_service_id == catalogue.id)
        )
    )).scalar_one_or_none()

    vector = "endpoint_agent"
    now = occurred_at or datetime.now(timezone.utc)

    if existing is not None:
        existing.last_seen_at = now
        sources = set(existing.discovery_sources or [])
        if vector not in sources:
            existing.discovery_sources = sorted(sources | {vector})
        # Don't broadcast on every poll — only the first time the EA
        # vector adds itself to an existing system.
        if vector not in (existing.discovery_sources or []):
            return None
        return None

    # New shadow system.
    system = AISystem(
        tenant_id=tenant_id,
        name=catalogue.name,
        catalogue_service_id=catalogue.id,
        provider_id=catalogue.provider_id,
        category=catalogue.category,
        subcategory=catalogue.subcategory,
        eu_ai_act_category=catalogue.eu_ai_act_cat,
        is_shadow=True,
        discovery_sources=[vector],
        first_discovered_at=now,
        last_seen_at=now,
        policy_status="monitor",
        tags=(catalogue.tags or []).copy(),
    )
    session.add(system)
    await session.flush()
    await session.refresh(system)

    return {
        "type": "new_system",
        "payload": {
            "id": str(system.id),
            "name": system.name,
            "category": system.category,
            "catalogue_slug": catalogue.catalogue_id,
            "first_discovered_at": now.isoformat(),
            "vector": vector,
            "detected_by_user": None,   # EA never sends user identity
            "department": None,
        },
    }


async def _resolve_catalogue(session, kind: str, payload: dict[str, Any]) -> AIService | None:
    """Look up a catalogue service row from the EA event payload.

    Strategy depends on the event kind:

      ai_provider_connection  Match `provider_domain` against
                              ai_services.browser_domains or any
                              api_endpoint_patterns entry that
                              CONTAINS the domain. Postgres ARRAY
                              membership for browser_domains, plus a
                              GIN-friendly text search on patterns.
      ai_process_running      Substring match on process_name against
                              ai_services.name (case-insensitive). We
                              keep this loose because OS-reported
                              binary names vary: cursor / cursor.exe /
                              Cursor / Cursor.app vs catalogue.name
                              "Cursor". One match wins (the catalogue
                              is curated; collisions don't happen for
                              the AI-binary set).
    """
    if kind == "ai_provider_connection":
        domain = (payload.get("provider_domain") or "").strip().lower()
        if not domain:
            return None
        # Direct hit on browser_domains array.
        row = (await session.execute(
            select(AIService).where(AIService.browser_domains.any(domain))
        )).scalar_one_or_none()
        if row is not None:
            return row
        # Try the api_endpoint_patterns array — patterns include host
        # prefixes (e.g. "api.openai.com/v1/chat/completions"). We
        # check whether any pattern starts with the domain.
        # Postgres: WHERE :domain = ANY(SELECT trim(...)). Simpler:
        # fetch candidate services that have api patterns and filter
        # in Python — the catalogue is small (<200 rows).
        rows = (await session.execute(
            select(AIService).where(AIService.api_endpoint_patterns.is_not(None))
        )).scalars().all()
        for r in rows:
            for pat in r.api_endpoint_patterns or []:
                if pat.lower().startswith(domain) or ("/" + domain) in pat.lower():
                    return r
        return None

    if kind == "ai_process_running":
        name = (payload.get("process_name") or "").strip().lower()
        if not name:
            return None
        # Strip Windows .exe and common suffixes for matching.
        bare = name
        for suffix in (".exe", ".app", "-cli", "-server"):
            if bare.endswith(suffix):
                bare = bare[: -len(suffix)]
        # Catalogue lookup: ai_services.id (e.g. "openai-cursor"
        # contains "cursor"), ai_services.name (e.g. "Cursor" lower
        # contains "cursor"). Pick the SHORTEST match so "claude"
        # wins over "claude-code-builder" when the binary is
        # literally `claude`.
        rows = (await session.execute(select(AIService))).scalars().all()
        best: AIService | None = None
        best_score = 99999
        for r in rows:
            cat_name = (r.name or "").lower()
            cat_id = (r.catalogue_id or "").lower()
            for hay in (cat_name, cat_id):
                if not hay:
                    continue
                if bare in hay or hay in bare:
                    score = abs(len(hay) - len(bare))
                    if score < best_score:
                        best, best_score = r, score
                    break
        return best

    return None
