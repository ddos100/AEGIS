"""FastAPI dependencies — DB session with RLS tenant context, current user, role gates."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, decode_token
from app.core.config import settings
from app.core.database import session_scope

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await decode_token(creds.credentials)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


async def get_db(user: CurrentUser) -> AsyncIterator[AsyncSession]:
    """Yield a DB session with RLS bound to the caller's tenant_id."""
    async with session_scope(tenant_id=user.tenant_id) as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]


def require_role(*allowed: str):
    """Dependency factory enforcing one of the given roles."""
    allowed_set = set(allowed)

    async def _guard(user: CurrentUser) -> AuthenticatedUser:
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(sorted(allowed_set))}",
            )
        return user

    return _guard


require_admin = require_role("admin")
require_analyst = require_role("admin", "analyst")


async def verify_ingest_key(x_ingest_key: Annotated[str | None, Header()] = None) -> None:
    """Ingest endpoints use a shared API key — not user JWT (high-throughput, machine-to-machine)."""
    if not x_ingest_key or x_ingest_key != settings.ingest_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest key")
