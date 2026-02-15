"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router
from app.config import get_settings
from app.models.database import engine
from app.services.cache_service import cache_service

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    # Startup
    logger.info("Starting Internal Knowledge Assistant …")
    await cache_service.connect()
    logger.info("Redis connected")

    # Verify PostgreSQL
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connected")

    yield

    # Shutdown
    await cache_service.disconnect()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Internal Knowledge Assistant",
    description=(
        "A multi-tenant RAG-powered assistant that answers employee questions "
        "using internal documents, with source citations and hallucination guards."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


# ── Health check (outside versioned prefix for infra probes) ─


@app.get("/health", tags=["infra"])
async def health_check():
    """Infrastructure health check for Docker / load balancers."""
    pg_ok = False
    redis_ok = False

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        pg_ok = True
    except Exception as exc:
        logger.error("PostgreSQL health check failed: %s", exc)

    redis_ok = await cache_service.ping()

    status = "healthy" if (pg_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "postgres": "ok" if pg_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "version": "1.0.0",
    }
