"""Liveness + readiness endpoints. Public (no auth)."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import healthcheck as db_healthcheck

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str  # populated in Phase 0 follow-up once redis client is wired


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = await db_healthcheck()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=settings.version,
        db="ok" if db_ok else "down",
        redis="unknown",
    )
