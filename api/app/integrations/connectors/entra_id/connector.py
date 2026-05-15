"""Microsoft Entra ID (Azure AD) connector — OAuth2 grant enumeration.

Discovers AI services that have been granted access via enterprise OIDC apps
in Entra ID. For every observed grant we:
  1. record an OAuthGrant row,
  2. match the OAuth app_id against the AI Service Catalogue's
     ``entra_app_ids`` array,
  3. if matched and no AISystem yet exists for that catalogue slug, auto-create
     a shadow record so the Registry surfaces it like any other discovery.

Required credentials::

    {
      "tenant_id":     "<azure-tenant-uuid>",
      "client_id":     "<app-registration-client-id>",
      "client_secret": "<app-registration-secret>"
    }

Required Graph application permissions (admin consent):
  - Directory.Read.All
  - Application.Read.All
  - AuditLog.Read.All
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import log
from app.integrations.connectors.base import BaseConnector, SyncResult, register_connector
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.idp_user import IdpUser
from app.models.oauth_grant import OAuthGrant

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_HOST = "https://login.microsoftonline.com"


@register_connector("entra_id", kind="idp")
class EntraIdConnector(BaseConnector):
    """Entra ID (Azure AD) — OAuth2 grants + AI app discovery via Graph."""

    # ---------- test ----------

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        try:
            token = await self._token(credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Token acquisition failed: {exc}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{GRAPH_BASE}/organization",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if r.status_code != 200:
                    return SyncResult(ok=False, error=f"Graph /organization → HTTP {r.status_code}: {r.text[:200]}")
                tenant = r.json().get("value", [{}])[0]
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Graph probe failed: {exc}")
        return SyncResult(ok=True, extra={"tenant_display_name": tenant.get("displayName")})

    # ---------- sync ----------

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        try:
            token = await self._token(credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Auth failed: {exc}")

        # Pull active OAuth2 permission grants. Each row carries the
        # clientId (the consenting app) and principalId (the user, for
        # delegated consent).
        try:
            grants = await self._fetch_all(token, "/oauth2PermissionGrants")
            apps = {a["id"]: a for a in await self._fetch_all(token, "/servicePrincipals?$select=id,appId,displayName,publisherName")}
            users = await self._fetch_all(token, "/users?$select=id,mail,displayName,department,jobTitle")
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Graph fetch failed: {exc}")

        # Build IdP user index
        user_by_id = {u["id"]: u for u in users}

        # Catalogue lookup — entra_app_ids -> AIService row
        cat_rows = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.entra_app_ids,
                   AIService.name, AIService.category, AIService.subcategory,
                   AIService.eu_ai_act_cat, AIService.provider_id, AIService.tags)
            .where(AIService.is_active.is_(True))
        )).all()
        appid_to_service: dict[str, dict] = {}
        for r in cat_rows:
            for app_id in r.entra_app_ids or []:
                appid_to_service[app_id] = dict(r._mapping)

        # Upsert idp_users + oauth_grants. Auto-create shadow AISystem rows
        # for any matched-but-not-registered services.
        new_count = 0
        updated_count = 0
        slug_to_system: dict[str, UUID] = {}

        for u in users:
            email = (u.get("mail") or "").lower()
            if not email:
                continue
            stmt = (
                pg_insert(IdpUser)
                .values(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    idp_user_id=u["id"],
                    email=email,
                    display_name=u.get("displayName"),
                    department=u.get("department"),
                    job_title=u.get("jobTitle"),
                    idp_groups=[],
                )
                .on_conflict_do_update(
                    constraint="uq_idp_users_unique",
                    set_={
                        "email":        email,
                        "display_name": u.get("displayName"),
                        "department":   u.get("department"),
                        "job_title":    u.get("jobTitle"),
                    },
                )
            )
            await session.execute(stmt)

        for g in grants:
            client_sp_id = g.get("clientId")
            sp = apps.get(client_sp_id) or {}
            app_id = sp.get("appId") or client_sp_id
            app_name = sp.get("displayName") or app_id
            catalogue_match = appid_to_service.get(app_id)

            idp_user_row = None
            if g.get("principalId"):
                u = user_by_id.get(g["principalId"])
                if u and u.get("mail"):
                    idp_user_row = (await session.execute(
                        select(IdpUser.id).where(
                            (IdpUser.integration_id == integration_id) &
                            (IdpUser.idp_user_id == u["id"])
                        )
                    )).scalar_one_or_none()

            ai_system_id = None
            if catalogue_match:
                slug = catalogue_match["catalogue_id"]
                if slug not in slug_to_system:
                    sys_id = await _ensure_shadow_system(
                        session, tenant_id, slug, catalogue_match, vector="idp",
                    )
                    if sys_id:
                        slug_to_system[slug] = sys_id
                ai_system_id = slug_to_system.get(slug)

            stmt = (
                pg_insert(OAuthGrant)
                .values(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    idp_user_id=idp_user_row,
                    app_id=app_id,
                    app_name=app_name,
                    app_publisher=sp.get("publisherName"),
                    granted_scopes=(g.get("scope") or "").split() if g.get("scope") else [],
                    consent_type=g.get("consentType"),
                    catalogue_match=catalogue_match["id"] if catalogue_match else None,
                    ai_system_id=ai_system_id,
                    raw_data=g,
                )
                .on_conflict_do_update(
                    constraint="uq_oauth_grants_unique",
                    set_={
                        "app_name":        app_name,
                        "app_publisher":   sp.get("publisherName"),
                        "granted_scopes":  (g.get("scope") or "").split() if g.get("scope") else [],
                        "catalogue_match": catalogue_match["id"] if catalogue_match else None,
                        "ai_system_id":    ai_system_id,
                        "raw_data":        g,
                    },
                )
            )
            res = await session.execute(stmt)
            if res.rowcount == 1:
                new_count += 1
            else:
                updated_count += 1

        log.info("aegis.entra_id.sync_complete",
                 grants=len(grants), apps=len(apps), users=len(users))
        return SyncResult(
            ok=True,
            discovered_count=len(grants),
            new_count=new_count,
            updated_count=updated_count,
            extra={"users": len(users), "apps": len(apps), "shadow_created": len(slug_to_system)},
        )

    # ---------- helpers ----------

    @retry(retry=retry_if_exception_type(httpx.HTTPError),
           wait=wait_exponential(multiplier=1, min=1, max=10),
           stop=stop_after_attempt(3),
           reraise=True)
    async def _token(self, creds: dict[str, Any]) -> str:
        for k in ("tenant_id", "client_id", "client_secret"):
            if not creds.get(k):
                raise ValueError(f"Missing credential field: {k}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{TOKEN_HOST}/{creds['tenant_id']}/oauth2/v2.0/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     creds["client_id"],
                    "client_secret": creds["client_secret"],
                    "scope":         "https://graph.microsoft.com/.default",
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    @staticmethod
    async def _fetch_all(token: str, path: str) -> list[dict]:
        """Follow Graph API @odata.nextLink pagination."""
        results: list[dict] = []
        url = f"{GRAPH_BASE}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 429:
                    await asyncio.sleep(int(r.headers.get("Retry-After", "5")))
                    continue
                r.raise_for_status()
                body = r.json()
                results.extend(body.get("value") or [])
                url = body.get("@odata.nextLink")
        return results


# Shared helper — also used by Okta and M365 connectors.

async def _ensure_shadow_system(session, tenant_id: UUID, slug: str,
                                catalogue_match: dict, *, vector: str) -> UUID | None:
    """If no AISystem exists for this catalogue slug + tenant, create one."""
    existing = (await session.execute(
        select(AISystem.id).where(
            (AISystem.tenant_id == tenant_id) &
            (AISystem.catalogue_service_id == catalogue_match["id"])
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    sys = AISystem(
        tenant_id=tenant_id,
        name=catalogue_match["name"],
        catalogue_service_id=catalogue_match["id"],
        provider_id=catalogue_match["provider_id"],
        category=catalogue_match["category"],
        subcategory=catalogue_match["subcategory"],
        eu_ai_act_category=catalogue_match["eu_ai_act_cat"],
        is_shadow=True,
        discovery_sources=[vector],
        policy_status="monitor",
        tags=(catalogue_match["tags"] or []).copy(),
    )
    session.add(sys)
    await session.flush()
    return sys.id
