"""AEGIS Endpoint Agent device-token signing (Phase 7.6).

The agent's bearer credential is a short self-describing token signed
by AEGIS with HMAC-SHA256:

    base64(payload).base64(signature)

`payload` is a JSON blob carrying:
    { "v": 1, "tenant_id": "...", "device_id": "...", "iat": <epoch> }

This avoids a heavyweight OAuth dance for a daemon that only ever talks
to one endpoint. The signing key is derived from the platform's
existing Fernet key material — the agent never sees the key. Token
revocation works by clearing endpoint_devices.revoked_at column; the
ingest route checks this on every request.

No PII in the token. No expiry (devices rotate by re-enrolment); the
fingerprint of the token is stored on the device row so an operator
can compare and revoke if an agent leaks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

from app.core.config import settings


_TOKEN_VERSION = 1


def _key() -> bytes:
    """Derive a stable signing key from FERNET_KEY.

    We don't reuse the Fernet key directly — instead we HKDF-style
    derive a per-purpose subkey. This keeps the device-token surface
    independent from the integration-credential encryption surface.
    """
    seed = (settings.fernet_key or "x" * 44).encode("utf-8")
    return hashlib.blake2b(seed, digest_size=32, person=b"aegis-ea-token").digest()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_dec(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def mint_device_token(*, tenant_id: UUID, device_id: UUID) -> str:
    payload = {
        "v":         _TOKEN_VERSION,
        "tenant_id": str(tenant_id),
        "device_id": str(device_id),
        "iat":       int(time.time()),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_key(), body, hashlib.sha256).digest()
    return f"{_b64u(body)}.{_b64u(sig)}"


def verify_device_token(token: str) -> dict[str, Any]:
    """Return the parsed payload after verifying the HMAC. Raises
    ValueError on malformed or invalid signature."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _b64u_dec(body_b64)
        sig  = _b64u_dec(sig_b64)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("malformed device token") from exc
    expected = hmac.new(_key(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid device token signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("malformed device token payload") from exc
    if payload.get("v") != _TOKEN_VERSION:
        raise ValueError("unsupported device token version")
    if "tenant_id" not in payload or "device_id" not in payload:
        raise ValueError("device token missing required claims")
    return payload


def token_fingerprint(token: str) -> str:
    """Stable sha256 fingerprint of a device token — stored on
    endpoint_devices.enrollment_fingerprint for revocation lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
