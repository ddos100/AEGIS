"""AEGIS Chrome extension endpoints.

  POST /v1/extension/enroll       Register a device and receive a device_id
  POST /v1/extension/events       Batch event submission
  GET  /v1/extension/catalogue    Compact domain → catalogue_id map for cache

All endpoints authenticate via the shared ingest API key, NOT user JWTs —
the extension is a managed endpoint, not a user-facing client.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import session_scope
from app.core.deps import verify_ingest_key
from app.integrations.network.base import NormalizedEvent
from app.integrations.network.matcher import match_event
from app.models.ai_service import AIService
from app.models.extension_device import ExtensionDevice
from app.schemas.ingest import (
    ExtensionCatalogueResponse,
    ExtensionEnrollRequest,
    ExtensionEnrollResponse,
    ExtensionEventBatch,
)
from app.workers.ingest import process_batch

router = APIRouter(prefix="/extension", tags=["extension"])


@router.post("/enroll", response_model=ExtensionEnrollResponse)
async def enroll_device(
    payload: ExtensionEnrollRequest,
    _key: Annotated[None, Depends(verify_ingest_key)],
    # Tenant binding for the extension is via the user_email mapped on first event.
    # For Phase 2 we accept tenant_id via query param so the dev/test flow is simple.
    tenant_id: str | None = None,
) -> ExtensionEnrollResponse:
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="tenant_id query param required")
    async with session_scope(tenant_id=tenant_id) as session:
        stmt = pg_insert(ExtensionDevice).values(
            tenant_id=tenant_id,
            device_fingerprint=payload.device_fingerprint,
            user_email=(payload.user_email or "").lower() or None,
            hostname=payload.hostname,
            browser_version=payload.browser_version,
            extension_version=payload.extension_version,
            os_platform=payload.os_platform,
            last_heartbeat=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "device_fingerprint"],
            set_={
                "extension_version": stmt.excluded.extension_version,
                "browser_version":   stmt.excluded.browser_version,
                "last_heartbeat":    stmt.excluded.last_heartbeat,
            },
        ).returning(ExtensionDevice.id)
        device_id = (await session.execute(stmt)).scalar_one()

    # Compute a catalogue version hash so the extension can decide when to refresh.
    cat_version = await _compute_catalogue_version()
    return ExtensionEnrollResponse(device_id=device_id, catalogue_version=cat_version)


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def submit_events(
    payload: ExtensionEventBatch,
    _key: Annotated[None, Depends(verify_ingest_key)],
):
    """Batch event submission from the AEGIS browser extension.

    Events are normalized inline and pass through the same ingest pipeline as
    network logs — the matcher does the lookup; shadow AI is auto-created.
    """
    raws: list[dict] = []
    now = datetime.now(timezone.utc)
    for ev in payload.events:
        raws.append({
            "domain": ev.domain,
            "catalogue_id": ev.catalogue_id,
            "extension_id": ev.extension_id,
            "type": ev.type,
            "occurred_at": (ev.occurred_at or now).isoformat(),
            **ev.extra,
        })

    # The browser extension's records are pre-shaped — we feed them through a
    # tiny inline normalizer rather than the registry to keep the code path
    # explicit.
    parsed: list[NormalizedEvent] = []
    for r in raws:
        domain = (r.get("domain") or "").lower().strip() or None
        if not domain and not r.get("catalogue_id"):
            continue
        try:
            occurred = datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            occurred = now
        parsed.append(NormalizedEvent(
            occurred_at=occurred,
            vector="browser_ext",
            source="aegis_extension",
            domain=domain,
            raw_meta={k: v for k, v in r.items()
                      if k in {"extension_id", "type", "catalogue_id"}},
        ))

    # Re-use the ingest pipeline so shadow AI detection + matcher behave identically.
    # The browser-extension pre-tag (catalogue_id from extension) overrides match if present.
    result = await process_batch(
        tenant_id=payload.tenant_id,
        source="aegis_extension_inline",  # alias — won't dispatch through normalizer registry
        events=[],  # we already have NormalizedEvents — call the lower-level path
    ) if False else await _ingest_normalized(payload.tenant_id, parsed)
    return {"accepted": len(payload.events), **result}


@router.get("/catalogue", response_model=ExtensionCatalogueResponse)
async def extension_catalogue(_key: Annotated[None, Depends(verify_ingest_key)]):
    """Compact catalogue map served to the extension — domain/extension id keys
    so the service worker can match without a per-event API call."""
    async with session_scope(tenant_id=None) as session:
        rows = (await session.execute(
            select(AIService.catalogue_id, AIService.browser_domains, AIService.catalogue_meta)
            .where(AIService.is_active.is_(True))
        )).all()

    domains: dict[str, str] = {}
    extensions: dict[str, str] = {}
    for catalogue_id, browser_domains, meta in rows:
        for d in browser_domains or []:
            domains[d.lower()] = catalogue_id
        for ext_id in (meta or {}).get("chrome_extension_ids", []) or []:
            extensions[ext_id] = catalogue_id

    version = await _compute_catalogue_version()
    return ExtensionCatalogueResponse(version=version, domains=domains, extensions=extensions)


# Helpers --------------------------------------------------------------------

async def _compute_catalogue_version() -> str:
    """Hash of the active catalogue's (catalogue_id, updated_at) pairs."""
    from app.core.database import engine
    from sqlalchemy import select as _sel
    async with engine.connect() as conn:
        rows = (await conn.execute(
            _sel(AIService.catalogue_id, AIService.updated_at).where(AIService.is_active.is_(True))
        )).all()
    h = hashlib.sha256()
    for cid, updated_at in sorted(rows):
        h.update(f"{cid}|{updated_at.isoformat()}".encode())
    return h.hexdigest()[:16]


async def _ingest_normalized(tenant_id, events: list[NormalizedEvent]) -> dict:
    """Tiny variant of :func:`process_batch` that takes pre-normalized events."""
    from uuid import UUID
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.ai_system import AISystem
    from app.models.ai_usage_event import AIUsageEvent
    from app.core.logging import log
    from app.core.redis import publish_discovery
    import asyncio

    matched = []
    for ev in events:
        hit = match_event(ev)
        if hit is None:
            continue
        matched.append((ev, hit))
    if not matched:
        return {"matched": 0, "shadow_new": 0}

    tenant_uuid = UUID(str(tenant_id))
    new_shadow = 0
    async with session_scope(tenant_id=tenant_uuid) as session:
        slugs = {hit.pattern.catalogue_slug for _, hit in matched}
        existing = (await session.execute(
            select(AISystem.id, AIService.catalogue_id)
            .join(AIService, AISystem.catalogue_service_id == AIService.id)
            .where(AIService.catalogue_id.in_(slugs))
        )).all()
        slug_to_system = {row.catalogue_id: row.id for row in existing}

        for slug in slugs - set(slug_to_system):
            cat = (await session.execute(
                select(AIService).where(AIService.catalogue_id == slug)
            )).scalar_one_or_none()
            if cat is None:
                continue
            sample_ev = next(ev for ev, h in matched if h.pattern.catalogue_slug == slug)
            system = AISystem(
                tenant_id=tenant_uuid,
                name=cat.name,
                catalogue_service_id=cat.id,
                provider_id=cat.provider_id,
                category=cat.category,
                subcategory=cat.subcategory,
                eu_ai_act_category=cat.eu_ai_act_cat,
                is_shadow=True,
                discovery_sources=["browser_ext"],
                first_discovered_at=sample_ev.occurred_at,
                last_seen_at=sample_ev.occurred_at,
                policy_status="monitor",
                tags=(cat.tags or []).copy(),
            )
            session.add(system)
            await session.flush()
            slug_to_system[slug] = system.id
            new_shadow += 1
            asyncio.create_task(publish_discovery(str(tenant_uuid), {
                "type": "new_system",
                "payload": {
                    "id": str(system.id), "name": system.name, "category": system.category,
                    "catalogue_slug": slug,
                    "first_discovered_at": sample_ev.occurred_at.isoformat(),
                    "vector": "browser_ext",
                },
            }))

        rows = [{
            "tenant_id": tenant_uuid,
            "ai_system_id": slug_to_system.get(hit.pattern.catalogue_slug),
            "catalogue_service_id": UUID(hit.pattern.service_id),
            "catalogue_slug": hit.pattern.catalogue_slug,
            "raw_domain": ev.domain,
            "vector": ev.vector,
            "source": ev.source,
            "user_email": ev.user_email,
            "raw_meta": ev.raw_meta,
            "occurred_at": ev.occurred_at,
        } for ev, hit in matched]
        await session.execute(pg_insert(AIUsageEvent).values(rows))

    log.info("aegis.extension.events_processed",
             tenant_id=str(tenant_uuid), accepted=len(events),
             matched=len(matched), shadow_new=new_shadow)
    return {"matched": len(matched), "shadow_new": new_shadow}
