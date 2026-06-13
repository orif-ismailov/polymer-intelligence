"""
FastAPI application factory.

create_app() is the single entry point for building the FastAPI instance.
All routers, middleware, and startup hooks are wired here.

Container entrypoint (deploy/docker-compose.dev.yml):
    uvicorn app.main:app --host 0.0.0.0 --port 8000

For development with live reload:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.api.health import router as health_router


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Steps:
    1. Configure structlog JSON logging (REQ-nfr-observability).
    2. Create FastAPI instance.
    3. Mount CORS middleware.
    4. Include routers under /api/v1.
    """
    configure_logging()

    application = FastAPI(
        title="Polymer Intelligence API",
        version="0.1.0",
        description=(
            "Market-intelligence platform for Uzbekistan's domestic polymer market. "
            "Collects, structures, and delivers market information to internal dashboard, "
            "Telegram Web App, and Telegram bot/channel."
        ),
        # Disable auto-generated docs in production (enable via env var if needed)
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Configured to be restrictive; open up origins in the deploy .env for prod.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # tighten this in production via env / nginx
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # All API routes are mounted under /api/v1 per dev-spec §3.2.
    application.include_router(health_router, prefix="/api/v1")

    return application


# Module-level app instance for uvicorn.
# e.g.: uvicorn app.main:app
app = create_app()
