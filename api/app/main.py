"""AEGIS FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, log
from app.routes import catalogue, health, me, registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1, environment=settings.env)
    log.info("aegis.api.startup", version=settings.version, env=settings.env)
    yield
    log.info("aegis.api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AEGIS API",
        version=settings.version,
        description="AI Enterprise Governance & Inventory System — backend API.",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(me.router, prefix=settings.api_v1_prefix)
    app.include_router(catalogue.router, prefix=settings.api_v1_prefix)
    app.include_router(registry.router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
