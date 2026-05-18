"""Zscaler ZIA mitigation adapter (Phase 7.5).

Implements the `block_url_category` primitive against Zscaler Internet
Access. Real-mode operations call:

  POST   {ZIA_BASE}/api/v1/urlCategories                 — create category
  PUT    {ZIA_BASE}/api/v1/urlCategories/{id}            — update urls
  POST   {ZIA_BASE}/api/v1/status/activate               — activate config

…using OAuth or legacy partner-key auth depending on tenant. Real-mode
code is not enabled in v1 — `dry_run = True` is the locked default. The
vendor calls are gated behind a per-deployment env flag flipped by
SCLLP onboarding once the customer's ZIA admin has provisioned
service-account credentials and a sandbox category for AEGIS to update.
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


@register(integration="zscaler", action="block_url_category")
class ZscalerBlockUrlCategoryAdapter(BaseMitigationAdapter):
    integration = "zscaler"
    action = "block_url_category"
    dry_run = True   # locked default per Phase 7.5 contract

    async def apply(self, *, credentials: dict[str, Any] | None,
                    params: dict[str, Any]) -> MitigationApplyResult:
        category = (params or {}).get("category")
        if not category:
            return MitigationApplyResult(
                ok=False, dry_run=self.dry_run,
                error="Missing required param: category",
            )
        # In dry-run we don't touch the vendor; we record a deterministic
        # vendor_ref so a later verify() can find "our" category by name.
        vendor_ref = f"ZIA-CAT-{hashlib.sha256(category.encode()).hexdigest()[:8]}"
        if self.dry_run:
            return MitigationApplyResult(
                ok=True, dry_run=True, vendor_ref=vendor_ref,
                detail=f"DRY-RUN: would create/update Zscaler URL category "
                        f"{category!r} and activate config",
                state_blob={"category": category, "vendor_ref": vendor_ref},
            )
        # Real-mode vendor call — guarded above by dry_run check.
        # (Real httpx PUT to /api/v1/urlCategories + POST /api/v1/status/activate)
        return MitigationApplyResult(
            ok=False, dry_run=False, error="real-mode not enabled in this build",
        )

    async def verify(self, *, credentials: dict[str, Any] | None,
                     params: dict[str, Any],
                     state_blob: dict[str, Any] | None) -> MitigationVerifyResult:
        if self.dry_run:
            return MitigationVerifyResult(
                verified=True, dry_run=True,
                detail=f"DRY-RUN: would GET /api/v1/urlCategories and confirm "
                        f"{(state_blob or {}).get('vendor_ref', '?')} is present",
            )
        return MitigationVerifyResult(
            verified=False, dry_run=False,
            error="real-mode verify not enabled in this build",
        )

    async def rollback(self, *, credentials: dict[str, Any] | None,
                       params: dict[str, Any],
                       state_blob: dict[str, Any] | None) -> MitigationApplyResult:
        ref = (state_blob or {}).get("vendor_ref")
        if self.dry_run:
            return MitigationApplyResult(
                ok=True, dry_run=True, vendor_ref=ref,
                detail=f"DRY-RUN: would remove urls from Zscaler URL category {ref}",
            )
        return MitigationApplyResult(
            ok=False, dry_run=False, error="real-mode rollback not enabled in this build",
        )


@register(integration="zscaler", action="rate_limit_url")
class ZscalerRateLimitUrlAdapter(BaseMitigationAdapter):
    """Throttle rather than block — used for cost-availability threats."""
    integration = "zscaler"
    action = "rate_limit_url"
    dry_run = True

    async def apply(self, *, credentials, params):
        domain = (params or {}).get("domain")
        limit  = (params or {}).get("limit_rpm")
        if not domain or not limit:
            return MitigationApplyResult(
                ok=False, dry_run=self.dry_run,
                error="Missing required params: domain, limit_rpm",
            )
        return MitigationApplyResult(
            ok=True, dry_run=True,
            vendor_ref=f"ZIA-BANDWIDTH-{hashlib.sha256(domain.encode()).hexdigest()[:8]}",
            detail=f"DRY-RUN: would create Zscaler bandwidth rule limiting "
                    f"{domain} to {limit} req/min",
            state_blob={"domain": domain, "limit_rpm": limit},
        )

    async def verify(self, *, credentials, params, state_blob):
        return MitigationVerifyResult(
            verified=True, dry_run=True,
            detail=f"DRY-RUN: would GET /api/v1/bandwidthControl/rules and "
                    f"confirm {(state_blob or {}).get('domain', '?')} rule present",
        )
