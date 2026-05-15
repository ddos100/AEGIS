"""Microsoft 365 Copilot connector — usage reports via Graph reports API.

Pulls daily Copilot usage detail. Each user with non-zero Copilot interactions
becomes an OAuthGrant pointing at the ``microsoft-copilot`` catalogue entry,
and the catalogue match auto-creates a shadow AISystem.

Required credentials (same shape as Entra ID; can re-use the same app
registration if it has the additional permission):

    {"tenant_id": "...", "client_id": "...", "client_secret": "..."}

Required Graph application permissions:
  - Reports.Read.All
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import log
from app.integrations.connectors.base import BaseConnector, SyncResult, register_connector
from app.integrations.connectors.entra_id.connector import EntraIdConnector, _ensure_shadow_system
from app.models.ai_service import AIService
from app.models.idp_user import IdpUser
from app.models.oauth_grant import OAuthGrant

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
COPILOT_REPORT_PATH = "/reports/getMicrosoft365CopilotUserDetail(period='D30')"
COPILOT_CATALOGUE_ID = "microsoft-copilot"


@register_connector("m365_copilot", kind="saas")
class M365CopilotConnector(BaseConnector):
    """M365 Copilot — usage detail via Graph reports API."""

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        # We re-use the Entra ID token machinery for auth.
        entra = EntraIdConnector()
        try:
            token = await entra._token(credentials)  # noqa: SLF001
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{GRAPH_BASE}{COPILOT_REPORT_PATH}",
                    headers={"Authorization": f"Bearer {token}"},
                    follow_redirects=True,
                )
                if r.status_code != 200:
                    return SyncResult(ok=False, error=f"Copilot report → HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))
        return SyncResult(ok=True)

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        entra = EntraIdConnector()
        try:
            token = await entra._token(credentials)  # noqa: SLF001
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.get(
                    f"{GRAPH_BASE}{COPILOT_REPORT_PATH}",
                    headers={"Authorization": f"Bearer {token}"},
                    follow_redirects=True,
                )
                r.raise_for_status()
                rows = list(csv.DictReader(io.StringIO(r.text)))
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Copilot fetch failed: {exc}")

        # Find the M365 Copilot catalogue row
        cat_row = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.name,
                   AIService.category, AIService.subcategory, AIService.eu_ai_act_cat,
                   AIService.provider_id, AIService.tags)
            .where(AIService.catalogue_id == COPILOT_CATALOGUE_ID)
        )).first()

        cat_dict = dict(cat_row._mapping) if cat_row else None
        ai_system_id: UUID | None = None
        if cat_dict:
            ai_system_id = await _ensure_shadow_system(
                session, tenant_id, COPILOT_CATALOGUE_ID, cat_dict, vector="saas",
            )

        # Active Copilot users → individual OAuthGrants
        active_users = 0
        for r in rows:
            email = (r.get("User Principal Name") or "").lower()
            if not email:
                continue
            # Skip users with zero activity (the report includes everyone licensed)
            if not any(int(r.get(col, "0") or "0") > 0
                       for col in r if col.lower().endswith("last activity date") is False
                       and col.endswith("(s)")):
                continue
            active_users += 1
            await session.execute(
                pg_insert(OAuthGrant)
                .values(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    app_id="microsoft-copilot",
                    app_name=f"Microsoft 365 Copilot ({email})",
                    app_publisher="Microsoft",
                    granted_scopes=["copilot"],
                    consent_type="admin",
                    catalogue_match=cat_dict["id"] if cat_dict else None,
                    ai_system_id=ai_system_id,
                    raw_data=r,
                )
                .on_conflict_do_update(
                    constraint="uq_oauth_grants_unique",
                    set_={
                        "raw_data":         r,
                        "ai_system_id":     ai_system_id,
                        "catalogue_match":  cat_dict["id"] if cat_dict else None,
                        "last_seen_at":     datetime.now(timezone.utc),
                    },
                )
            )

        log.info("aegis.m365_copilot.sync_complete",
                 rows=len(rows), active=active_users)
        return SyncResult(
            ok=True,
            discovered_count=len(rows),
            new_count=active_users,
            extra={"active_users": active_users,
                   "shadow_created": 1 if ai_system_id and cat_dict else 0},
        )
