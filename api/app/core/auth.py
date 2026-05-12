"""JWT validation via Keycloak JWKS.

Phase 0 implementation: we validate signatures against the Keycloak realm JWKS,
extract tenant_id from a custom claim, and expose a Pydantic model for downstream
dependencies.
"""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.core.config import settings

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL_SECONDS = 3600


class AuthenticatedUser(BaseModel):
    sub: str = Field(..., description="Keycloak subject UUID")
    email: str
    tenant_id: UUID
    role: str = Field(default="viewer", description="admin | analyst | viewer")
    full_name: str | None = None
    groups: list[str] = Field(default_factory=list)
    raw_claims: dict[str, Any] = Field(default_factory=dict)


async def _fetch_jwks() -> dict[str, Any]:
    global _JWKS_CACHE, _JWKS_FETCHED_AT
    now = time.time()
    if _JWKS_CACHE and (now - _JWKS_FETCHED_AT) < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(settings.jwks_url)
        resp.raise_for_status()
        _JWKS_CACHE = resp.json()
        _JWKS_FETCHED_AT = now
    return _JWKS_CACHE


async def decode_token(token: str) -> AuthenticatedUser:
    """Validate a JWT against Keycloak JWKS and return an AuthenticatedUser."""
    try:
        jwks = await _fetch_jwks()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signing key not found")

        claims = jwt.decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.keycloak_audience,
            issuer=settings.jwt_issuer,
            options={"leeway": settings.jwt_leeway_seconds},
        )
    except JWTError as exc:  # invalid signature / expired / malformed
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc

    tenant_claim = claims.get("tenant_id") or claims.get("https://aegis/tenant_id")
    if not tenant_claim:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing tenant_id claim")

    return AuthenticatedUser(
        sub=claims["sub"],
        email=claims.get("email", ""),
        tenant_id=UUID(tenant_claim),
        role=claims.get("role") or _role_from_realm_access(claims),
        full_name=claims.get("name"),
        groups=claims.get("groups", []),
        raw_claims=claims,
    )


def _role_from_realm_access(claims: dict[str, Any]) -> str:
    """Extract an AEGIS role from Keycloak realm_access.roles claim."""
    roles = claims.get("realm_access", {}).get("roles", [])
    for candidate in ("admin", "analyst", "viewer"):
        if f"aegis:{candidate}" in roles or candidate in roles:
            return candidate
    return "viewer"
