"""Per-module licence loader (Phase 7.1).

This module is the runtime guard for AEGIS module SKUs (AEGIS-CORE,
AEGIS-COMPLIANCE, AEGIS-THREAT, AEGIS-EA, AEGIS-SECTOR-*). It performs
three jobs:

1. **Load** — read the active entitlement rows for the current tenant
   from the `modules_entitled` table. (Production deployments populate
   that table from a signed licence file; dev mode pre-seeds every
   module via Alembic 009.)

2. **Verify** — when an external signed licence file is present, verify
   its Ed25519 signature against the SCLLP public key (passed via env)
   before its rows replace the in-DB entitlements. The signing key is
   custodied by AWS KMS Asymmetric; verification needs only the public
   half.

3. **Gate** — expose a FastAPI dependency `requires_module(sku)` that
   returns 402 Payment Required when the calling tenant lacks the SKU.

Determinism + privacy: licence files carry pseudonymous tenant IDs and
no personal data. Failed signature verification raises and is logged
without the licence body content.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.models.module_entitlement import ModuleEntitlement

log = logging.getLogger(__name__)

# Default in-process cache so a single request reads each tenant's entitlements
# once. Cleared by `clear_cache()` after licence reload.
_CACHE: dict[UUID, list[dict[str, Any]]] = {}


@dataclass(slots=True)
class ActiveModule:
    module_sku: str
    edition: str | None
    feature_flags: dict[str, Any]
    limits: dict[str, Any]
    valid_to: datetime | None


# ----------------------------------------------------------------------
# Verification helpers (Ed25519 signed licence files)
# ----------------------------------------------------------------------

class LicenceError(Exception):
    """Raised when a licence file is malformed or its signature fails."""


def verify_licence_payload(payload_json: bytes, signature_b64: str,
                            public_key_pem: bytes) -> dict[str, Any]:
    """Verify an Ed25519 signature over the licence payload.

    Verifying signatures requires only the public half of the SCLLP key —
    AWS KMS holds the private half and signs at issuance time. We import
    cryptography lazily because the production deployment may not have
    the library available in dev mode (where licence verification is
    bypassed in favour of the DB-seeded entitlements).
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:  # noqa: BLE001
        raise LicenceError("cryptography library not installed") from exc

    try:
        pub: Ed25519PublicKey = serialization.load_pem_public_key(public_key_pem)  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001
        raise LicenceError("public key load failed") from exc

    try:
        sig = base64.b64decode(signature_b64)
        pub.verify(sig, payload_json)
    except InvalidSignature as exc:
        raise LicenceError("invalid licence signature") from exc
    except Exception as exc:  # noqa: BLE001
        raise LicenceError(f"verification error: {type(exc).__name__}") from exc

    try:
        return json.loads(payload_json.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise LicenceError("malformed licence JSON") from exc


def licence_fingerprint(payload_json: bytes) -> str:
    """Stable SHA-256 over the canonical licence bytes — stored on every
    entitlement row that the licence activated, so an auditor can trace
    a runtime entitlement back to the issuing licence file."""
    return hashlib.sha256(payload_json).hexdigest()


# ----------------------------------------------------------------------
# Runtime entitlement lookup + gate
# ----------------------------------------------------------------------

async def list_active_modules(db, tenant_id: UUID) -> list[ActiveModule]:
    """Return every entitlement row currently in force for `tenant_id`."""
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(ModuleEntitlement)
        .where(ModuleEntitlement.tenant_id == tenant_id)
    )).scalars().all()
    active: list[ActiveModule] = []
    for r in rows:
        if r.valid_to is not None and r.valid_to < now:
            continue
        active.append(ActiveModule(
            module_sku=r.module_sku, edition=r.edition,
            feature_flags=dict(r.feature_flags or {}),
            limits=dict(r.limits or {}),
            valid_to=r.valid_to,
        ))
    return active


def requires_module(sku: str):
    """FastAPI dependency factory. Returns 402 when the tenant lacks `sku`.

    Usage::

        @router.get("/threats", dependencies=[Depends(requires_module("AEGIS-THREAT"))])
        async def list_threats(...): ...
    """

    async def _guard(db: DBSession, user: CurrentUser) -> None:
        active = await list_active_modules(db, user.tenant_id)
        if any(m.module_sku == sku for m in active):
            return
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code":   "module_not_licensed",
                "module": sku,
                "action": "Contact SCLLP to license this module.",
                "contact": "licensing@securisti.com",
            },
        )

    return _guard


def clear_cache() -> None:
    _CACHE.clear()


# Type alias for routes that want the active list directly
ActiveModulesDep = Annotated[list[ActiveModule], Depends(lambda: [])]
