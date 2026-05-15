"""GCP AI connector — Vertex AI endpoints + Cloud AI APIs via Cloud Asset Inventory.

Cloud Asset Inventory gives us org-/folder-/project-wide visibility in a
single query, exactly like Azure Resource Graph. We enumerate every asset
type that maps to an AI service.

Required credentials::

    {
      "service_account_json": "<JSON string of the SA key>",
      "parent": "projects/PROJECT_ID"   # or "organizations/ORG_ID" / "folders/FOLDER_ID"
    }

Required IAM (project-/org-level Reader is enough):
  - roles/cloudasset.viewer
"""
from __future__ import annotations

import asyncio
import json
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

# Asset types we care about. Cloud Asset Inventory uses Google's type-naming
# convention — most AI resources live in aiplatform.googleapis.com.
GCP_AI_ASSET_TYPES = [
    "aiplatform.googleapis.com/Endpoint",
    "aiplatform.googleapis.com/Model",
    "aiplatform.googleapis.com/PublisherModel",
    "ml.googleapis.com/Job",
    "discoveryengine.googleapis.com/Engine",      # Vertex AI Agent Builder
    "speech.googleapis.com/Operation",
]


@register_connector("gcp", kind="cloud")
class GcpConnector(BaseConnector):
    """GCP Vertex AI + Cloud AI inventory via Cloud Asset Inventory."""

    # ---------- test ----------

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        try:
            self._validate(credentials)
            await asyncio.to_thread(self._build_client, credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))
        return SyncResult(ok=True)

    # ---------- sync ----------

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        try:
            self._validate(credentials)
            rows = await asyncio.to_thread(self._enum, credentials)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))

        # Catalogue match — Vertex Endpoint → google-gemini (the most likely
        # backing model in 2026). Operators can re-map per record manually.
        cat_rows = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.name,
                   AIService.category, AIService.subcategory, AIService.eu_ai_act_cat,
                   AIService.provider_id, AIService.tags)
            .where(AIService.catalogue_id.in_(("google-gemini", "google-vertex-ai")))
        )).all()
        by_slug = {r.catalogue_id: dict(r._mapping) for r in cat_rows}

        new_count = updated_count = 0
        slug_to_system: dict[str, UUID] = {}
        for r in rows:
            cat = by_slug.get("google-vertex-ai") or by_slug.get("google-gemini")
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
                    cloud_provider="gcp",
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    resource_name=r.get("resource_name"),
                    region=r.get("region"),
                    project_id=r.get("project_id"),
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

        log.info("aegis.gcp.sync_complete",
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
        if not creds.get("service_account_json"):
            raise ValueError("Missing credential field: service_account_json")
        if not creds.get("parent"):
            raise ValueError("Missing credential field: parent "
                             "(e.g. projects/PROJECT_ID)")

    @staticmethod
    def _build_client(creds: dict[str, Any]):
        from google.cloud import asset_v1  # type: ignore[import-not-found]
        from google.oauth2 import service_account  # type: ignore[import-not-found]
        sa_info = json.loads(creds["service_account_json"]) if isinstance(
            creds["service_account_json"], str) else creds["service_account_json"]
        gcred = service_account.Credentials.from_service_account_info(sa_info)
        return asset_v1.AssetServiceClient(credentials=gcred)

    @staticmethod
    def _enum(creds: dict[str, Any]) -> list[dict]:
        client = GcpConnector._build_client(creds)
        # Lazy import for the request type.
        from google.cloud import asset_v1  # type: ignore[import-not-found]
        req = asset_v1.ListAssetsRequest(
            parent=creds["parent"],
            asset_types=GCP_AI_ASSET_TYPES,
            content_type=asset_v1.ContentType.RESOURCE,
        )
        rows: list[dict] = []
        for asset in client.list_assets(request=req):
            atype = asset.asset_type
            data = asset.resource.data if asset.resource and asset.resource.data else {}
            display = data.get("displayName") or data.get("name") or asset.name
            location = data.get("location") or (asset.resource.location if asset.resource else None)
            project = (asset.name or "").split("/")[1] if (asset.name or "").startswith("//cloudresourcemanager") \
                      else (asset.name or "").split("/projects/")[1].split("/")[0] \
                      if "/projects/" in (asset.name or "") else None
            service = atype.split("/")[0]
            resource_type = (
                "vertex_endpoint"     if atype.endswith("/Endpoint") else
                "vertex_model"        if atype.endswith("/Model") else
                "vertex_publisher_model" if atype.endswith("/PublisherModel") else
                "ml_engine_job"       if atype.endswith("/Job") else
                "discovery_engine"    if atype.endswith("/Engine") else atype
            )
            rows.append({
                "resource_type": resource_type,
                "resource_id":   asset.name,
                "resource_name": display,
                "region":        location,
                "project_id":    project,
                "service_name":  service.split(".")[0],
                "model_id":      data.get("model"),
                "status":        data.get("state") or data.get("deploymentState"),
                "tags":          data.get("labels") or {},
                "raw_data":      {"asset_type": atype, "version": data.get("versionId")},
            })
        return rows
