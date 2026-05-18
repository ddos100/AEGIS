"""Cloudflare Gateway / Zero Trust mitigation adapter (Phase 7.5).

Implements DNS + HTTP policy primitives. Real-mode operations call:

  POST /accounts/{id}/gateway/rules                — create gateway rule
  POST /accounts/{id}/gateway/lists                — create list of FQDNs
  PUT  /accounts/{id}/gateway/rules/{rid}          — update rule
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.integrations.mitigations.base import (
    BaseMitigationAdapter,
    MitigationApplyResult,
    MitigationVerifyResult,
    register,
)


def _ref(label: str) -> str:
    return f"CF-GW-{hashlib.sha256(label.encode()).hexdigest()[:8]}"


@register(integration="cloudflare_gateway", action="block_dns_category")
class CloudflareGatewayBlockDnsCategoryAdapter(BaseMitigationAdapter):
    integration = "cloudflare_gateway"
    action = "block_dns_category"
    dry_run = True

    async def apply(self, *, credentials, params):
        category = (params or {}).get("category")
        if not category:
            return MitigationApplyResult(
                ok=False, dry_run=self.dry_run,
                error="Missing required param: category",
            )
        vref = _ref(f"dns:{category}")
        return MitigationApplyResult(
            ok=True, dry_run=True, vendor_ref=vref,
            detail=f"DRY-RUN: would create Cloudflare Gateway DNS rule "
                    f"blocking category {category!r}",
            state_blob={"category": category, "vendor_ref": vref, "scope": "dns"},
        )

    async def verify(self, *, credentials, params, state_blob):
        vref = (state_blob or {}).get("vendor_ref", "?")
        return MitigationVerifyResult(
            verified=True, dry_run=True,
            detail=f"DRY-RUN: would GET /accounts/.../gateway/rules and confirm "
                    f"{vref} present + enabled",
        )

    async def rollback(self, *, credentials, params, state_blob):
        vref = (state_blob or {}).get("vendor_ref", "?")
        return MitigationApplyResult(
            ok=True, dry_run=True, vendor_ref=vref,
            detail=f"DRY-RUN: would DELETE Cloudflare Gateway rule {vref}",
        )


@register(integration="cloudflare_gateway", action="block_url")
class CloudflareGatewayBlockUrlAdapter(CloudflareGatewayBlockDnsCategoryAdapter):
    integration = "cloudflare_gateway"
    action = "block_url"

    async def apply(self, *, credentials, params):
        url_pattern = (params or {}).get("url_pattern")
        if not url_pattern:
            return MitigationApplyResult(
                ok=False, dry_run=self.dry_run,
                error="Missing required param: url_pattern",
            )
        vref = _ref(f"http:{url_pattern}")
        return MitigationApplyResult(
            ok=True, dry_run=True, vendor_ref=vref,
            detail=f"DRY-RUN: would create Cloudflare Gateway HTTP rule blocking "
                    f"url_pattern={url_pattern!r}",
            state_blob={"url_pattern": url_pattern, "vendor_ref": vref, "scope": "http"},
        )
