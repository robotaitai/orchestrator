"""Commander Demo - FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from commander.api.http import router as http_router
from commander.api.ws import router as ws_router, start_ws_broadcast, stop_ws_broadcast
from commander.core.logging import setup_logging
from commander.core.orchestrator import get_orchestrator
from commander.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # ── Startup ──────────────────────────────────────────────────────────────
    logger = logging.getLogger("commander")
    logger.info("=" * 60)
    logger.info(f"  {settings.app_name} v{settings.app_version}")
    logger.info("=" * 60)
    logger.info(f"  Host: {settings.host}:{settings.port}")
    logger.info(f"  Debug: {settings.debug}")
    logger.info(f"  Log Level: {settings.log_level}")
    logger.info(f"  Sim Tick Rate: {settings.sim_tick_rate}s")
    logger.info(f"  Gemini Model: {settings.gemini_model}")
    logger.info(f"  Gemini API Key: {'configured' if settings.gemini_api_key else 'NOT SET'}")
    logger.info("=" * 60)

    # Initialize and start orchestrator
    orchestrator = get_orchestrator()
    await orchestrator.start()
    logger.info(f"Orchestrator started with {len(orchestrator.fleet_state.platforms)} platforms")

    # Start WebSocket broadcast
    await start_ws_broadcast()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down Commander...")
    stop_ws_broadcast()
    await orchestrator.stop()
    logger.info("Orchestrator stopped")


# ──────────────────────────────────────────────────────────────────────────────
# Application Setup
# ──────────────────────────────────────────────────────────────────────────────

# Configure logging before creating the app
setup_logging(
    level=settings.log_level,
    log_dir=settings.log_dir if not settings.debug else None,
    json_format=settings.log_json,
)

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="LLM-powered robot orchestration demo with MuJoCo simulation",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware (permissive for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(http_router, prefix="/api/v1", tags=["api"])
app.include_router(ws_router, tags=["websocket"])


# ──────────────────────────────────────────────────────────────────────────────
# Root Endpoints (outside /api/v1 for convenience)
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with welcome message."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else "disabled",
    }


@app.get("/health")
async def health_root() -> dict[str, str]:
    """Root-level health check (alias for /api/v1/health)."""
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the application via uvicorn."""
    uvicorn.run(
        "commander.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
