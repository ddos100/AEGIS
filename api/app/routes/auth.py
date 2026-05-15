"""Authentication proxy — fronts Keycloak so the browser never needs to know
the OIDC realm internals, and lets us mint an opaque rotating session ID that
changes on every refresh without ever forcing the user back to a login screen.

Endpoints
---------
    POST /v1/auth/login        { username, password }   -> tokens + session_id
    POST /v1/auth/refresh      { refresh_token }        -> rotated tokens + session_id
    POST /v1/auth/logout       { refresh_token }        -> 204
    GET  /v1/auth/sources                              -> visible discovery sources

Rotating session ID
-------------------
The `session_id` returned alongside each token bundle is a deterministic hash
of (sub, jti) from the access token. Because Keycloak issues a fresh `jti`
on every grant *and* on every refresh, the session_id rotates on every call
to /refresh — but the underlying refresh_token chain keeps the user logged
in indefinitely (until the offline session TTL expires). The frontend stores
the chain in localStorage and rotates silently every ~10 minutes.

The login form posts username+password to /v1/auth/login (never to Keycloak
directly): that keeps the realm + client_id out of the SPA.
"""
from __future__ import annotations

import hashlib
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentUser
from app.integrations.network.base import registered_sources

router = APIRouter(prefix="/auth", tags=["auth"])

# Keycloak token endpoint (internal URL — server-to-server inside the cluster).
_TOKEN_URL = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
_LOGOUT_URL = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/logout"


# ---------- request / response shapes ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenBundle(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int = Field(..., description="Seconds until access_token expires")
    refresh_expires_in: int = Field(..., description="Seconds until refresh_token expires")
    token_type: str = "Bearer"
    session_id: str = Field(..., description="Opaque rotating session identifier")


class DiscoverySource(BaseModel):
    source: str
    vector: str
    mode: str
    cls: str


# ---------- helpers ----------

def _session_id_from_access(access_token: str) -> str:
    """Compute a deterministic-but-opaque rotating session ID from the access token.

    Keycloak emits a fresh `jti` on every grant + refresh, so this rotates on
    every refresh call without exposing any token material to the frontend.
    """
    try:
        # No verification — we only need the public claims for the hash.
        claims = jwt.get_unverified_claims(access_token)
    except Exception:  # noqa: BLE001
        return hashlib.sha256(access_token.encode()).hexdigest()[:32]
    sub = claims.get("sub") or claims.get("preferred_username") or "anon"
    jti = claims.get("jti") or claims.get("iat") or ""
    return hashlib.sha256(f"{sub}|{jti}".encode()).hexdigest()[:32]


def _bundle_from_keycloak(payload: dict[str, Any]) -> TokenBundle:
    """Convert a Keycloak token response into a TokenBundle."""
    try:
        return TokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload.get("expires_in", 900)),
            refresh_expires_in=int(payload.get("refresh_expires_in", 1800)),
            token_type=payload.get("token_type", "Bearer"),
            session_id=_session_id_from_access(payload["access_token"]),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Malformed Keycloak token response (missing {exc!s})",
        ) from exc


async def _post_to_keycloak(url: str, form: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            return await client.post(
                url,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Keycloak unreachable: {exc!s}",
            ) from exc


# ---------- routes ----------

@router.post("/login", response_model=TokenBundle)
async def login(req: LoginRequest) -> TokenBundle:
    """Exchange username + password for a token bundle.

    Uses Resource Owner Password Credentials grant against the public
    `aegis-web` client (no client secret). Production deployments should
    front this with rate limiting and lockout (handled at the ingress layer).
    """
    resp = await _post_to_keycloak(_TOKEN_URL, {
        "grant_type": "password",
        "client_id": "aegis-web",
        "username": req.username,
        "password": req.password,
        "scope": "openid profile email",
    })
    if resp.status_code != 200:
        # Forward Keycloak's specific error so the UI can show "invalid credentials"
        # vs. "user disabled" without leaking too much detail.
        detail = "Invalid credentials"
        try:
            kc_err = resp.json()
            if kc_err.get("error_description"):
                detail = kc_err["error_description"]
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    return _bundle_from_keycloak(resp.json())


@router.post("/refresh", response_model=TokenBundle)
async def refresh(req: RefreshRequest) -> TokenBundle:
    """Rotate the access + refresh tokens.

    Called silently by the SPA every ~10 minutes (well before the 15-minute
    access-token TTL). Keycloak's default refresh-token rotation also issues
    a new refresh_token on every call, so even the long-lived part of the
    chain rotates — there is no static credential held in the browser.
    """
    resp = await _post_to_keycloak(_TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": "aegis-web",
        "refresh_token": req.refresh_token,
    })
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token rejected — please sign in again",
        )
    return _bundle_from_keycloak(resp.json())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: LogoutRequest) -> None:
    """Revoke the refresh token at Keycloak.

    Best-effort: even if Keycloak rejects the revocation we return 204 so the
    frontend can always clear its local state.
    """
    if not req.refresh_token:
        return
    try:
        await _post_to_keycloak(_LOGOUT_URL, {
            "client_id": "aegis-web",
            "refresh_token": req.refresh_token,
        })
    except HTTPException:
        return


@router.get("/sources", response_model=list[DiscoverySource])
async def list_discovery_sources(user: CurrentUser) -> list[DiscoverySource]:  # noqa: ARG001
    """Authenticated, read-only inventory of every registered network/XDR source.

    Used by the Integrations UI to render the "Discovery sources" catalogue
    so admins can see exactly which vendors AEGIS can ingest from today.
    """
    return [
        DiscoverySource(source=src, vector=meta["vector"], mode=meta["mode"], cls=meta["class"])
        for src, meta in sorted(registered_sources().items())
    ]
