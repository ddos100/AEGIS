"""Azure AI connector — Cognitive Services + Azure OpenAI + ML workspaces.

Uses azure-mgmt-resource (via the Resource Graph API) to enumerate every AI
control-plane resource in one query, regardless of subscription/RG layout.
This is faster than walking subscriptions sequentially with individual SDK
clients and avoids us needing N separate library imports.

Required credentials::

    {
      "tenant_id":     "<azure-ad-tenant-uuid>",
      "client_id":     "<service-principal-app-id>",
      "client_secret": "<service-principal-secret>",
      "subscription_ids": ["<sub-1>", "<sub-2>"]    # optional; defaults to all
    }

Required Azure RBAC (read-only):
  - Reader on each target subscription
  - Resource Graph queries require no additional permission beyond Reader.

Resource types enumerated:
  - Microsoft.CognitiveServices/accounts
      (including kind=OpenAI for Azure OpenAI deployments)
  - Microsoft.MachineLearningServices/workspaces
  - Microsoft.Search/searchServices  (AI Search)

The sync is sync (synchronous SDK); we run it in a thread executor so
the asyncio event loop stays responsive.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import log
from app.integrations.connectors.base import BaseConnector, SyncResult, register_connector
from app.integrations.connectors.entra_id.connector import _ensure_shadow_system
from app.models.ai_service import AIService
from app.models.cloud_ai_resource import CloudAIResource

# Resource Graph KQL — single query covers all relevant types.
AZURE_AI_KQL = """
Resources
| where type =~ 'microsoft.cognitiveservices/accounts'
   or type =~ 'microsoft.machinelearningservices/workspaces'
   or type =~ 'microsoft.search/searchservices'
| project id, name, type, kind, location, subscriptionId, resourceGroup,
          tags, properties, sku
"""


@register_connector("azure", kind="cloud")
class AzureConnector(BaseConnector):
    """Azure — Cognitive Services + Azure OpenAI + ML workspaces inventory."""

    # ---------- test ----------

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        try:
            self._validate(credentials)
            # Lazy import keeps the test suite happy when azure SDKs aren't installed.
            from azure.identity import ClientSecretCredential
            cred = ClientSecretCredential(
                tenant_id=credentials["tenant_id"],
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
            )
            # Fetch a token to confirm the SP works.
            await asyncio.to_thread(cred.get_token, "https://management.azure.com/.default")
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))
        return SyncResult(ok=True)

    # ---------- sync ----------

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        try:
            self._validate(credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))

        # Heavy lifting in a thread — azure SDKs are sync.
        try:
            rows = await asyncio.to_thread(self._enum_via_resource_graph, credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=f"Azure Resource Graph query failed: {exc}")

        # Catalogue match: Azure OpenAI → microsoft-copilot (best fit for now).
        # Future iteration could add an explicit catalogue entry per Azure model.
        catalogue_rows = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.name,
                   AIService.category, AIService.subcategory, AIService.eu_ai_act_cat,
                   AIService.provider_id, AIService.tags)
            .where(AIService.catalogue_id.in_(
                ("microsoft-copilot", "azure-openai", "azure-cognitive-services")
            ))
        )).all()
        by_slug = {r.catalogue_id: dict(r._mapping) for r in catalogue_rows}

        new_count = updated_count = 0
        slug_to_system: dict[str, UUID] = {}
        for r in rows:
            cat = self._classify(r, by_slug)
            ai_system_id = None
            if cat:
                slug = cat["catalogue_id"]
                if slug not in slug_to_system:
                    sys_id = await _ensure_shadow_system(session, tenant_id, slug, cat, vector="cloud")
                    if sys_id:
                        slug_to_system[slug] = sys_id
                ai_system_id = slug_to_system.get(slug)

            stmt = (
                pg_insert(CloudAIResource)
                .values(
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    cloud_provider="azure",
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    resource_name=r.get("resource_name"),
                    region=r.get("region"),
                    account_id=r.get("subscription_id"),
                    service_name=r.get("service_name"),
                    model_id=r.get("model_id"),
                    status=r.get("status"),
                    tags=r.get("tags") or {},
                    catalogue_match=cat["id"] if cat else None,
                    ai_system_id=ai_system_id,
                    raw_data=r.get("raw_data") or {},
                    last_scanned_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    constraint="uq_cloud_ai_resources_unique",
                    set_={
                        "resource_name":   r.get("resource_name"),
                        "status":          r.get("status"),
                        "tags":            r.get("tags") or {},
                        "catalogue_match": cat["id"] if cat else None,
                        "ai_system_id":    ai_system_id,
                        "raw_data":        r.get("raw_data") or {},
                        "last_scanned_at": datetime.now(timezone.utc),
                    },
                )
            )
            res = await session.execute(stmt)
            if res.rowcount == 1:
                new_count += 1
            else:
                updated_count += 1

        log.info("aegis.azure.sync_complete",
                 discovered=len(rows), shadow_created=len(slug_to_system))
        return SyncResult(
            ok=True,
            discovered_count=len(rows),
            new_count=new_count,
            updated_count=updated_count,
            extra={"shadow_created": len(slug_to_system)},
        )

    # ---------- helpers (sync, run via to_thread) ----------

    @staticmethod
    def _validate(creds: dict[str, Any]) -> None:
        for k in ("tenant_id", "client_id", "client_secret"):
            if not creds.get(k):
                raise ValueError(f"Missing credential field: {k}")

    @staticmethod
    def _enum_via_resource_graph(creds: dict[str, Any]) -> list[dict]:
        """Run the KQL query via Azure Resource Graph.

        Returns a list of normalised dicts shaped like the AWS connector's
        records so the upsert loop in sync() is identical across clouds.
        """
        # Imports inside the function so the api container can be built without
        # the Azure SDKs when the connector isn't used.
        from azure.identity import ClientSecretCredential
        from azure.mgmt.resourcegraph import ResourceGraphClient
        from azure.mgmt.resourcegraph.models import QueryRequest

        cred = ClientSecretCredential(
            tenant_id=creds["tenant_id"],
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
        )
        client = ResourceGraphClient(credential=cred)

        req = QueryRequest(
            query=AZURE_AI_KQL,
            subscriptions=creds.get("subscription_ids") or None,
        )
        resp = client.resources(req)

        rows: list[dict] = []
        for r in resp.data or []:
            rid     = r.get("id")
            rtype   = (r.get("type") or "").lower()
            kind    = (r.get("kind") or "").lower()
            props   = r.get("properties") or {}
            service_name = "azure_openai" if kind == "openai" else (
                "cognitive_services" if "cognitiveservices" in rtype else
                "ml_workspace"       if "machinelearningservices" in rtype else
                "ai_search"          if "search" in rtype else "azure_ai"
            )
            resource_type = (
                "azure_openai_deployment" if kind == "openai" else
                "cognitive_services_account" if "cognitiveservices" in rtype else
                "ml_workspace"           if "machinelearningservices" in rtype else
                "ai_search_service"      if "search" in rtype else rtype
            )
            rows.append({
                "resource_type": resource_type,
                "resource_id":   rid,
                "resource_name": r.get("name"),
                "region":        r.get("location"),
                "subscription_id": r.get("subscriptionId"),
                "service_name":  service_name,
                "model_id":      props.get("model", {}).get("name") if isinstance(props.get("model"), dict) else None,
                "status":        props.get("provisioningState"),
                "tags":          r.get("tags") or {},
                "raw_data":      {
                    "kind":           kind, "sku": r.get("sku"),
                    "resource_group": r.get("resourceGroup"),
                    "endpoint":       props.get("endpoint"),
                },
            })
        return rows

    @staticmethod
    def _classify(record: dict, by_slug: dict[str, dict]) -> dict | None:
        kind = (record.get("raw_data") or {}).get("kind", "").lower()
        if record["service_name"] == "azure_openai" or kind == "openai":
            return by_slug.get("azure-openai") or by_slug.get("microsoft-copilot")
        if record["service_name"] == "cognitive_services":
            return by_slug.get("azure-cognitive-services") or by_slug.get("microsoft-copilot")
        return by_slug.get("microsoft-copilot")
