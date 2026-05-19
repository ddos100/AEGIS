"""Tiny helper shared across all dry-run mitigation adapters.

Lets each new vendor adapter stay focused on documenting the real-mode
vendor API call rather than re-writing the dry-run dance + vendor_ref
hashing + state_blob plumbing every time.

Usage:

    from app.integrations.mitigations._drylib import dry_apply, dry_verify

    @register(integration="palo_alto", action="block_url_category")
    class PAN(BaseMitigationAdapter):
        async def apply(self, *, credentials, params):
            return dry_apply(
                prefix="PAN-CAT",
                required=["category"],
                params=params,
                detail_tmpl="would push Palo Alto custom URL category {category!r} via Panorama",
            )
        async def verify(self, *, credentials, params, state_blob):
            return dry_verify("Panorama custom URL categories", state_blob)
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.integrations.mitigations.base import (
    MitigationApplyResult,
    MitigationVerifyResult,
)


def vendor_ref(prefix: str, key: str) -> str:
    """Deterministic vendor-side ID — same input always yields the same
    ref, so verify()/rollback() can locate the exact change."""
    return f"{prefix}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]}"


def dry_apply(
    *,
    prefix: str,
    required: list[str],
    params: dict[str, Any] | None,
    detail_tmpl: str,
    key_field: str | None = None,
) -> MitigationApplyResult:
    """Generic dry-run apply.

    Validates required params, derives a deterministic vendor_ref from
    `key_field` (or the first required param), and returns a
    MitigationApplyResult with `dry_run=True`. The detail string is
    rendered via str.format(**params) so each adapter controls its own
    operator-facing message.
    """
    p = params or {}
    missing = [k for k in required if k not in p or p[k] in (None, "", [])]
    if missing:
        return MitigationApplyResult(
            ok=False, dry_run=True,
            error=f"Missing required param(s): {', '.join(missing)}",
        )
    key_value = p[key_field or required[0]]
    if isinstance(key_value, (list, tuple)):
        key_value = ",".join(str(x) for x in key_value)
    vref = vendor_ref(prefix, str(key_value))
    try:
        detail = "DRY-RUN: " + detail_tmpl.format(**p)
    except (KeyError, IndexError):  # pragma: no cover - defensive
        detail = "DRY-RUN: " + detail_tmpl
    return MitigationApplyResult(
        ok=True, dry_run=True, vendor_ref=vref,
        detail=detail,
        state_blob={"vendor_ref": vref, **p},
    )


def dry_verify(api_label: str, state_blob: dict[str, Any] | None) -> MitigationVerifyResult:
    """Generic dry-run verify — emits a 'would GET …' detail line so the
    operator can see what AEGIS will check at the vendor when real-mode
    flips on."""
    sb = state_blob or {}
    ref = sb.get("vendor_ref", "?")
    return MitigationVerifyResult(
        verified=True, dry_run=True,
        detail=f"DRY-RUN: would query {api_label} and confirm {ref} present",
    )


def dry_rollback(api_label: str, state_blob: dict[str, Any] | None) -> MitigationApplyResult:
    sb = state_blob or {}
    ref = sb.get("vendor_ref", "?")
    return MitigationApplyResult(
        ok=True, dry_run=True, vendor_ref=ref,
        detail=f"DRY-RUN: would remove {ref} from {api_label}",
    )
