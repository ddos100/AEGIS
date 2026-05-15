"""AWS connector — Bedrock + SageMaker + Comprehend AI service inventory.

Uses boto3 in a thread executor (boto3 is sync; we offload to keep the event
loop responsive). All sessions are scoped by STS AssumeRole — AEGIS never
receives long-lived IAM keys when the client follows the recommended setup.

Required credentials (one of two flavours)::

    # 1. Long-lived IAM user (dev only)
    {"access_key_id": "...", "secret_access_key": "...", "regions": ["ap-south-1","us-east-1"]}

    # 2. STS AssumeRole (recommended for production)
    {"assume_role_arn": "arn:aws:iam::123456789012:role/AegisReadOnly",
     "external_id": "...", "regions": ["ap-south-1","us-east-1"],
     "session_name": "aegis-sync"}

Required IAM permissions (read-only):
  - bedrock:ListFoundationModels, bedrock:ListProvisionedModelThroughputs
  - sagemaker:ListEndpoints, sagemaker:DescribeEndpoint
  - comprehend:ListEndpoints, rekognition:ListCollections (optional)
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


@register_connector("aws", kind="cloud")
class AwsConnector(BaseConnector):
    """AWS Bedrock + SageMaker AI inventory via boto3."""

    async def test(self, credentials: dict[str, Any]) -> SyncResult:
        try:
            sess = await asyncio.to_thread(self._session, credentials)
            sts = sess.client("sts")
            ident = await asyncio.to_thread(sts.get_caller_identity)
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))
        return SyncResult(ok=True, extra={
            "account_id": ident.get("Account"),
            "arn":        ident.get("Arn"),
        })

    async def sync(self, credentials: dict[str, Any], *, tenant_id: UUID,
                   integration_id: UUID, session) -> SyncResult:
        try:
            sess = await asyncio.to_thread(self._session, credentials)
            account_id = (await asyncio.to_thread(
                sess.client("sts").get_caller_identity)).get("Account")
        except Exception as exc:  # noqa: BLE001
            return SyncResult(ok=False, error=str(exc))

        regions = credentials.get("regions") or ["us-east-1"]
        discovered: list[dict] = []
        for region in regions:
            try:
                discovered += await asyncio.to_thread(self._enum_bedrock, sess, region, account_id)
                discovered += await asyncio.to_thread(self._enum_sagemaker, sess, region, account_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("aegis.aws.region_scan_failed", region=region, error=str(exc))

        # Catalogue match — Bedrock entries are tagged with provider_slug=amazon
        cat_rows = (await session.execute(
            select(AIService.id, AIService.catalogue_id, AIService.name,
                   AIService.category, AIService.subcategory, AIService.eu_ai_act_cat,
                   AIService.provider_id, AIService.tags)
            .where(AIService.catalogue_id == "amazon-bedrock")
        )).all()
        bedrock_cat = dict(cat_rows[0]._mapping) if cat_rows else None

        new_count = updated_count = 0
        slug_to_system: dict[str, UUID] = {}
        for r in discovered:
            cat = bedrock_cat if r["service_name"] == "bedrock" else None
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
                    cloud_provider="aws",
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    resource_name=r.get("resource_name"),
                    region=r.get("region"),
                    account_id=r.get("account_id"),
                    service_name=r.get("service_name"),
                    model_id=r.get("model_id"),
                    status=r.get("status"),
                    usage_metrics=r.get("usage_metrics") or {},
                    tags=r.get("tags") or {},
                    catalogue_match=cat["id"] if cat else None,
                    ai_system_id=ai_system_id,
                    raw_data=r.get("raw_data") or {},
                    last_scanned_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    constraint="uq_cloud_ai_resources_unique",
                    set_={
                        "resource_name":    r.get("resource_name"),
                        "status":           r.get("status"),
                        "usage_metrics":    r.get("usage_metrics") or {},
                        "tags":             r.get("tags") or {},
                        "catalogue_match":  cat["id"] if cat else None,
                        "ai_system_id":     ai_system_id,
                        "raw_data":         r.get("raw_data") or {},
                        "last_scanned_at":  datetime.now(timezone.utc),
                    },
                )
            )
            res = await session.execute(stmt)
            if res.rowcount == 1:
                new_count += 1
            else:
                updated_count += 1

        log.info("aegis.aws.sync_complete",
                 regions=regions, discovered=len(discovered),
                 shadow_created=len(slug_to_system))
        return SyncResult(
            ok=True,
            discovered_count=len(discovered),
            new_count=new_count,
            updated_count=updated_count,
            extra={"regions": regions, "shadow_created": len(slug_to_system)},
        )

    # ---------- sync helpers (run in threads) ----------

    @staticmethod
    def _session(creds: dict[str, Any]):
        import boto3
        if creds.get("assume_role_arn"):
            base = boto3.Session(
                aws_access_key_id=creds.get("access_key_id"),
                aws_secret_access_key=creds.get("secret_access_key"),
            )
            sts = base.client("sts")
            params: dict[str, Any] = {
                "RoleArn":         creds["assume_role_arn"],
                "RoleSessionName": creds.get("session_name", "aegis-sync"),
                "DurationSeconds": 3600,
            }
            if creds.get("external_id"):
                params["ExternalId"] = creds["external_id"]
            resp = sts.assume_role(**params)
            c = resp["Credentials"]
            return boto3.Session(
                aws_access_key_id=c["AccessKeyId"],
                aws_secret_access_key=c["SecretAccessKey"],
                aws_session_token=c["SessionToken"],
            )
        if creds.get("access_key_id"):
            return boto3.Session(
                aws_access_key_id=creds["access_key_id"],
                aws_secret_access_key=creds["secret_access_key"],
            )
        raise ValueError("AWS credentials missing both assume_role_arn and access_key_id")

    @staticmethod
    def _enum_bedrock(sess, region: str, account_id: str) -> list[dict]:
        try:
            client = sess.client("bedrock", region_name=region)
            models = client.list_foundation_models().get("modelSummaries", [])
        except Exception:
            return []
        out = []
        for m in models:
            out.append({
                "resource_type": "bedrock_model",
                "resource_id":   m.get("modelArn") or f"bedrock:{m.get('modelId')}:{region}",
                "resource_name": m.get("modelName") or m.get("modelId"),
                "region":        region,
                "account_id":    account_id,
                "service_name":  "bedrock",
                "model_id":      m.get("modelId"),
                "status":        m.get("modelLifecycle", {}).get("status"),
                "raw_data":      m,
            })
        return out

    @staticmethod
    def _enum_sagemaker(sess, region: str, account_id: str) -> list[dict]:
        try:
            client = sess.client("sagemaker", region_name=region)
            paginator = client.get_paginator("list_endpoints")
            endpoints = []
            for page in paginator.paginate():
                endpoints += page.get("Endpoints", [])
        except Exception:
            return []
        out = []
        for ep in endpoints:
            out.append({
                "resource_type": "sagemaker_endpoint",
                "resource_id":   ep.get("EndpointArn") or f"sagemaker:{ep.get('EndpointName')}:{region}",
                "resource_name": ep.get("EndpointName"),
                "region":        region,
                "account_id":    account_id,
                "service_name":  "sagemaker",
                "status":        ep.get("EndpointStatus"),
                "raw_data":      {k: str(v) for k, v in ep.items()},
            })
        return out
