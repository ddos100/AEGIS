"""Current-user endpoint — returns the caller's profile from JWT claims."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import CurrentUser

router = APIRouter(prefix="/me", tags=["me"])


class MeResponse(BaseModel):
    sub: str
    email: str
    tenant_id: str
    role: str
    full_name: str | None
    groups: list[str]


@router.get("", response_model=MeResponse)
async def get_me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        sub=user.sub,
        email=user.email,
        tenant_id=str(user.tenant_id),
        role=user.role,
        full_name=user.full_name,
        groups=user.groups,
    )
