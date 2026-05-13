"""Async ingest pipeline — turns a batch of raw events into matched usage rows.

This module is used by:
  - the POST /v1/ingest/network endpoint (inline batch processing)
  - Celery's ``process_log_batch`` task (offloaded high-volume processing)

The pipeline:

  1. Normalize  — pick the registered normalizer for `source` and parse every raw record.
  2. Match      — run each NormalizedEvent through the Aho-Corasick matcher.
                   Drop records that don't match the catalogue (not AI traffic).
  3. Persist    — bulk insert matched events into ai_usage_events.
  4. Shadow AI  — for every distinct catalogue_slug seen, if no AISystem
                   exists for this tenant yet, create one with is_shadow=True
                   and broadcast on the tenant's Redis discovery channel.

Each step is a separate function so the test suite can exercise them in
isolation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import session_scope
from app.core.logging import log
from app.core.redis import publish_discovery
from app.integrations.network.base import NormalizedEvent, get_normalizer
from app.integrations.network.matcher import MatchResult, match_event
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent


async def process_batch(
    *,
    tenant_id: UUID,
    source: str,
    events: list[Any],
) -> dict[str, int]:
    """Run a single batch through the full pipeline. Returns counts dict."""
    normalizer = get_normalizer(source)
    parsed: list[tuple[NormalizedEvent, MatchResult]] = []

    for raw in events:
        ev = normalizer.parse(raw)
        if ev is None:
            continue
        hit = match_event(ev)
        if hit is None:
            continue
        parsed.append((ev, hit))

    if not parsed:
        return {"accepted": len(events), "matched": 0, "shadow_new": 0}

    new_shadow_count = 0
    async with session_scope(tenant_id=tenant_id) as session:
        # Look up which catalogue slugs already have a registry entry for this tenant.
        slugs_seen = {hit.pattern.catalogue_slug for _ev, hit in parsed}
        existing_rows = (
            await session.execute(
                select(AISystem.id, AIService.catalogue_id)
                .join(AIService, AISystem.catalogue_service_id == AIService.id)
                .where(AIService.catalogue_id.in_(slugs_seen))
            )
        ).all()
        slug_to_system: dict[str, UUID] = {row.catalogue_id: row.id for row in existing_rows}

        # Create shadow records for slugs we don't have yet.
        for slug in slugs_seen - set(slug_to_system):
            system_id = await _create_shadow_system(session, slug, tenant_id, parsed)
            if system_id is not None:
                slug_to_system[slug] = system_id
                new_shadow_count += 1

        # Bulk insert usage events.
        rows = []
        for ev, hit in parsed:
            rows.append({
                "tenant_id": tenant_id,
                "ai_system_id": slug_to_system.get(hit.pattern.catalogue_slug),
                "catalogue_service_id": UUID(hit.pattern.service_id),
                "catalogue_slug": hit.pattern.catalogue_slug,
                "raw_domain": ev.domain,
                "raw_url_path": ev.url_path,
                "vector": ev.vector,
                "source": ev.source,
                "user_email": ev.user_email,
                "department": ev.department,
                "source_ip": ev.source_ip,
                "hostname": ev.hostname,
                "process_name": ev.process_name,
                "process_hash": ev.process_hash,
                "bytes_sent": ev.bytes_sent,
                "bytes_recv": ev.bytes_recv,
                "request_count": ev.request_count,
                "session_id": ev.session_id,
                "raw_meta": ev.raw_meta,
                "occurred_at": ev.occurred_at,
            })
        if rows:
            stmt = pg_insert(AIUsageEvent).values(rows)
            await session.execute(stmt)

    log.info(
        "aegis.ingest.batch_processed",
        tenant_id=str(tenant_id),
        source=source,
        accepted=len(events),
        matched=len(parsed),
        new_shadow=new_shadow_count,
    )
    return {"accepted": len(events), "matched": len(parsed), "shadow_new": new_shadow_count}


async def _create_shadow_system(
    session, slug: str, tenant_id: UUID,
    parsed: list[tuple[NormalizedEvent, MatchResult]],
) -> UUID | None:
    """Create a shadow AISystem record + broadcast over Redis."""
    # Find any matched record for this slug (we need its discovery context).
    sample_ev, sample_hit = next(((e, h) for e, h in parsed
                                  if h.pattern.catalogue_slug == slug), (None, None))
    if sample_ev is None or sample_hit is None:
        return None

    catalogue = (
        await session.execute(select(AIService).where(AIService.catalogue_id == slug))
    ).scalar_one_or_none()
    if catalogue is None:
        return None

    system = AISystem(
        tenant_id=tenant_id,
        name=catalogue.name,
        catalogue_service_id=catalogue.id,
        provider_id=catalogue.provider_id,
        category=catalogue.category,
        subcategory=catalogue.subcategory,
        eu_ai_act_category=catalogue.eu_ai_act_cat,
        is_shadow=True,
        discovery_sources=[sample_ev.vector],
        first_discovered_at=sample_ev.occurred_at,
        last_seen_at=sample_ev.occurred_at,
        policy_status="monitor",
        tags=(catalogue.tags or []).copy(),
    )
    session.add(system)
    await session.flush()
    await session.refresh(system)

    # Await the broadcast — previously we used asyncio.create_task() which
    # could be cancelled when the request handler returned before the publish
    # completed. The cost of awaiting is ~1ms (redis publish over loopback),
    # and we'd rather pay it than silently lose Shadow AI Radar updates.
    # Failures here must NOT roll back the DB insert.
    try:
        await publish_discovery(str(tenant_id), {
            "type": "new_system",
            "payload": {
                "id": str(system.id),
                "name": system.name,
                "category": system.category,
                "catalogue_slug": slug,
                "first_discovered_at": sample_ev.occurred_at.isoformat(),
                "vector": sample_ev.vector,
                "detected_by_user": sample_ev.user_email,
                "department": sample_ev.department,
            },
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("aegis.discovery.publish_failed", error=str(exc),
                    tenant_id=str(tenant_id), slug=slug)
    return system.id
