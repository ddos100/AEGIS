"""Okta connector — SAML/OIDC enterprise application enumeration.

Discovers AI services that have been added as enterprise apps in Okta and
records each user assignment as an OAuth-equivalent grant.

Required credentials::

    {
      "okta_domain": "<your-org>.okta.com",
      "api_token":   "<okta-api-token>"   # read-only admin role recommended
    }

Required Okta permissions: read on apps, users, and group/user app assignments.
The connector uses the Okta `/api/v1/apps` and `/api/v1/apps/{id}/users`
endpoints.

Catalogue match strategy (since Okta doesn't expose a stable client_id the way
Entra ID does):
  - The app's `signOnMode` + `label` is matched against the catalogue
    `entra_app_ids` array (treated as a list of well-known Okta IDs / labels).
  - Operators can extend per-tenant by tagging Okta apps in the catalogue
    YAML's ``catalogue_meta.okta_labels`` field (future work).
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
from app.integrations.connectors.entra_id.connector import _ensure_shadow_system
from app.models.ai_service import AIService
from app.models.idp_user import IdpUser
from app.models.oauth_grant import OAuthGrant


@register_connector("okta", kind="idp")
class OktaConnector(BaseConnector):
    """Okta — SAML/OIDC AI enterprise-app discovery."""

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        try:
            self._validate(credentials)
            async with self._client(credentials) as client:
                r = await client.get("/api/v1/org")
                if r.status_code != 200:
                    return SyncResult(ok=False, error=f"Okta /api/v1/org → HTTP {r.status_code}: {r.text[:200]}")
                org = r.json()
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))
        return SyncResult(ok=True, extra={"org_name": org.get("companyName")})

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        try:
            self._validate(credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))

        # Fetch apps + users in parallel
        try:
            async with self._client(credentials) as client:
                apps_task = self._paginated(client, "/api/v1/apps")
                users_task = self._paginated(client, "/api/v1/users")
                apps, users = await asyncio.gather(apps_task, users_task)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Okta fetch failed: {exc}")

        # Catalogue: match by entra_app_ids (treated as label list) or by
        # one of the browser_domains substrings being in the app's label/name.
        cat_rows = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.entra_app_ids,
                   AIService.browser_domains, AIService.name, AIService.category,
                   AIService.subcategory, AIService.eu_ai_act_cat, AIService.provider_id,
                   AIService.tags)
            .where(AIService.is_active.is_(True))
        )).all()

        def match_app(app: dict) -> dict | None:
            label_lower = (app.get("label") or "").lower()
            for row in cat_rows:
                ids = (row.entra_app_ids or [])
                if app.get("id") in ids or label_lower in {i.lower() for i in ids}:
                    return dict(row._mapping)
                for dom in row.browser_domains or []:
                    if dom and dom.split(".")[0] in label_lower:
                        return dict(row._mapping)
            return None

        # IdP user upserts
        for u in users:
            profile = u.get("profile") or {}
            email = (profile.get("email") or "").lower()
            if not email:
                continue
            await session.execute(
                pg_insert(IdpUser)
                .values(
                    tenant_id=tenant_id, integration_id=integration_id,
                    idp_user_id=u["id"], email=email,
                    display_name=profile.get("login") or profile.get("firstName"),
                    department=profile.get("department"),
                    job_title=profile.get("title"),
                    idp_groups=[],
                )
                .on_conflict_do_update(
                    constraint="uq_idp_users_unique",
                    set_={
                        "email": email,
                        "display_name": profile.get("login"),
                        "department": profile.get("department"),
                        "job_title": profile.get("title"),
                    },
                )
            )

        # Grants (one per app — Okta enterprise apps are tenant-scoped, not per-user grants)
        new_count = updated_count = 0
        slug_to_system: dict[str, UUID] = {}
        for app in apps:
            if app.get("status") != "ACTIVE":
                continue
            cat = match_app(app)
            ai_system_id = None
            if cat:
                slug = cat["catalogue_id"]
                if slug not in slug_to_system:
                    sys_id = await _ensure_shadow_system(session, tenant_id, slug, cat, vector="idp")
                    if sys_id:
                        slug_to_system[slug] = sys_id
                ai_system_id = slug_to_system.get(slug)

            stmt = (
                pg_insert(OAuthGrant)
                .values(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    idp_user_id=None,
                    app_id=app["id"],
                    app_name=app.get("label") or app.get("name") or app["id"],
                    app_publisher=app.get("signOnMode"),
                    granted_scopes=[],
                    consent_type="admin",
                    catalogue_match=cat["id"] if cat else None,
                    ai_system_id=ai_system_id,
                    raw_data={
                        "signOnMode": app.get("signOnMode"),
                        "name":       app.get("name"),
                        "status":     app.get("status"),
                        "features":   app.get("features"),
                    },
                )
                .on_conflict_do_update(
                    constraint="uq_oauth_grants_unique",
                    set_={
                        "app_name":         app.get("label") or app.get("name") or app["id"],
                        "app_publisher":    app.get("signOnMode"),
                        "catalogue_match":  cat["id"] if cat else None,
                        "ai_system_id":     ai_system_id,
                    },
                )
            )
            res = await session.execute(stmt)
            if res.rowcount == 1:
                new_count += 1
            else:
                updated_count += 1

        log.info("aegis.okta.sync_complete",
                 apps=len(apps), users=len(users), matched=len(slug_to_system))
        return SyncResult(
            ok=True,
            discovered_count=len(apps),
            new_count=new_count,
            updated_count=updated_count,
            extra={"users": len(users), "shadow_created": len(slug_to_system)},
        )

    # ---------- helpers ----------

    @staticmethod
    def _validate(creds: dict[str, Any]) -> None:
        for k in ("okta_domain", "api_token"):
            if not creds.get(k):
                raise ValueError(f"Missing credential field: {k}")

    @staticmethod
    def _client(creds: dict[str, Any]) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"https://{creds['okta_domain']}",
            headers={"Authorization": f"SSWS {creds['api_token']}",
                     "Accept":        "application/json"},
            timeout=30.0,
        )

    @staticmethod
    @retry(retry=retry_if_exception_type(httpx.HTTPError),
           wait=wait_exponential(multiplier=1, min=1, max=10),
           stop=stop_after_attempt(3),
           reraise=True)
    async def _paginated(client: httpx.AsyncClient, path: str) -> list[dict]:
        """Follow Okta Link: rel='next' pagination."""
        results: list[dict] = []
        url = path
        while url:
            r = await client.get(url)
            if r.status_code == 429:
                await asyncio.sleep(int(r.headers.get("X-Rate-Limit-Reset", "5")))
                continue
            r.raise_for_status()
            results.extend(r.json() or [])
            # parse Link header
            link = r.headers.get("link") or r.headers.get("Link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1:part.find(">")]
                    break
            url = next_url
        return results
