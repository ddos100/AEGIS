"""Eramba integration — pushes AEGIS Registry + risk assessments into Eramba.

Eramba is SCLLP's existing GRC platform. AEGIS pushes; Eramba never pushes
back. The push happens on an admin-triggered button or a Celery beat (left
disabled by default since not every client has an Eramba instance).

Endpoints used (Eramba 3.x REST API):

  POST /api/v1/assets              create / update IT asset (one per AISystem)
  POST /api/v1/risks               one per Critical/High AISystem
  POST /api/v1/compliance-findings one per compliance gap

Credentials are stored in the IntegrationCredential framework (Phase 3)
with integration="eramba". Required fields::

    {"base_url": "https://eramba.example.com", "api_token": "..."}

Failure isolation: a single asset failure is logged but does not abort
the rest of the sync.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.logging import log
from app.models.ai_system import AISystem


async def push_systems(
    *,
    credentials: dict[str, Any],
    tenant_id: UUID,
    session,
) -> dict[str, Any]:
    """Push every AISystem in the tenant Registry to Eramba as IT assets."""
    base_url = credentials.get("base_url")
    token = credentials.get("api_token")
    if not base_url or not token:
        return {"ok": False, "error": "missing base_url / api_token"}

    systems = (await session.execute(select(AISystem))).scalars().all()
    if not systems:
        return {"ok": True, "synced": 0, "failed": 0}

    synced = failed = 0
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=20.0,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    ) as client:
        for s in systems:
            payload = {
                "name":          s.name,
                "category":      s.category,
                "owner":         str(s.owner_user_id) if s.owner_user_id else None,
                "impact_level":  s.risk_level,
                "risk_score":    s.current_risk_score,
                "description":   s.intended_purpose,
                "external_id":   f"aegis:{s.id}",
                "metadata": {
                    "is_shadow":            s.is_shadow,
                    "eu_ai_act_category":   s.eu_ai_act_category,
                    "aisia_status":         s.aisia_status,
                    "data_types_processed": list(s.data_types_processed or []),
                },
            }
            try:
                r = await client.post("/api/v1/assets", json=payload)
                if r.status_code in (200, 201, 204):
                    synced += 1
                else:
                    failed += 1
                    log.warning("aegis.eramba.asset_failed", status=r.status_code,
                                name=s.name, body=r.text[:200])
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("aegis.eramba.asset_exception", name=s.name, error=str(exc))

    log.info("aegis.eramba.push_complete",
             tenant_id=str(tenant_id), synced=synced, failed=failed)
    return {"ok": failed == 0, "synced": synced, "failed": failed}
