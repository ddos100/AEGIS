"""AEGIS FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, log
from app.integrations.connectors import load_all_connectors
from app.integrations.network.base import load_all_normalizers
from app.integrations.network.matcher import load_from_db, matcher_size
from app.routes import (
    aisia, auth, catalogue, compliance, dashboard, discovery, eramba, exposures,
    extension, health, ingest, integrations, me, mitigations, policies, registry,
    reports, risk, threats,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1, environment=settings.env)
    load_all_normalizers()
    load_all_connectors()
    try:
        await load_from_db()
        log.info("aegis.matcher.loaded", **matcher_size())
    except Exception as exc:  # noqa: BLE001 — DB may not be ready in tests; that's fine
        log.warning("aegis.matcher.load_failed", error=str(exc))
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
    p = settings.api_v1_prefix
    app.include_router(health.router,    prefix=p)
    app.include_router(auth.router,      prefix=p)
    app.include_router(me.router,        prefix=p)
    app.include_router(catalogue.router, prefix=p)
    app.include_router(registry.router,  prefix=p)
    app.include_router(ingest.router,    prefix=p)
    app.include_router(extension.router, prefix=p)
    app.include_router(discovery.router, prefix=p)
    app.include_router(integrations.router, prefix=p)
    app.include_router(risk.router,         prefix=p)
    app.include_router(aisia.router,        prefix=p)
    app.include_router(policies.router,     prefix=p)
    app.include_router(compliance.router,   prefix=p)
    app.include_router(reports.router,      prefix=p)
    app.include_router(dashboard.router,    prefix=p)
    app.include_router(eramba.router,       prefix=p)
    app.include_router(threats.router,          prefix=p)
    app.include_router(threats.licence_router,  prefix=p)
    app.include_router(exposures.router,        prefix=p)
    app.include_router(mitigations.router,      prefix=p)
    return app


app = create_app()
