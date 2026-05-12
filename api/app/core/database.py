"""Async SQLAlchemy engine, session factory, and RLS-aware session helper."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# One engine per process. We use NullPool in tests; defaults are fine for app code.
engine = create_async_engine(
    str(settings.database_url),
    echo=False,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

# Session factory — expire_on_commit=False so models stay usable post-commit in async handlers.
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(tenant_id: UUID | None = None) -> AsyncIterator[AsyncSession]:
    """Open a session and set the tenant RLS context (if provided).

    Every API request flows through this so PostgreSQL RLS policies receive the
    correct ``app.current_tenant`` setting and enforce isolation transparently.
    """
    async with SessionLocal() as session:
        if tenant_id is not None:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def healthcheck() -> bool:
    """Lightweight DB ping — used by /v1/health."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
