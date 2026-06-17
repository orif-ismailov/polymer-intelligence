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

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_sources import router as admin_sources_router
from app.api.auth import router as auth_router
from app.api.deps import require_admin, require_analyst_or_admin
from app.api.feed import router as feed_router
from app.api.health import router as health_router
from app.api.telegram_webhook import router as telegram_webhook_router
from app.api.webapp.requests import router as webapp_requests_router
from app.api.webapp.me import router as webapp_me_router
from app.api.webapp.files import router as webapp_files_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.models.staff import StaffUser

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup/shutdown hook.

    On startup, when settings.RUN_MIGRATIONS_ON_STARTUP is true, apply the locked
    schema via the advisory-locked runner in app.entrypoint (SC#2 — a fresh
    `docker compose up` migrates a clean database without a manual step). The flag
    defaults false so the TestClient-built app in the suite/CI never attempts to
    reach a database it does not have. Concurrent api workers serialize on the
    pg advisory lock; `alembic upgrade head` is idempotent once at head.
    """
    if settings.RUN_MIGRATIONS_ON_STARTUP:
        from app.entrypoint import run_migrations  # noqa: PLC0415 — avoid import-time cost in tests

        revision = run_migrations()
        logger.info("startup.migrations_applied", extra={"revision": revision})

    # Register the Telegram bot webhook + persistent Web App menu button.
    # Guarded by PUBLIC_WEBAPP_URL — empty in dev/test so Telegram is never called
    # without a live deployment. In production (PUBLIC_WEBAPP_URL set in .env),
    # this runs once per api-container startup (idempotent — Telegram accepts
    # re-registration of the same webhook URL).
    if settings.PUBLIC_WEBAPP_URL:
        from telegram.bot import setup_webhook  # noqa: PLC0415

        await setup_webhook()
        logger.info("lifespan.telegram_webhook_registered")

    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Steps:
    1. Configure structlog JSON logging (REQ-nfr-observability).
    2. Create FastAPI instance.
    3. Mount CORS middleware.
    4. Include routers under /api/v1.
    """
    configure_logging()

    # WR-03: gate OpenAPI docs behind settings.DEBUG so the full API schema
    # (endpoints, request/response models, security requirements) is not publicly
    # accessible in production. Set DEBUG=true in .env for local development.
    _docs_url = "/docs" if settings.DEBUG else None
    _redoc_url = "/redoc" if settings.DEBUG else None
    _openapi_url = "/openapi.json" if settings.DEBUG else None

    application = FastAPI(
        title="Polymer Intelligence API",
        version="0.1.0",
        description=(
            "Market-intelligence platform for Uzbekistan's domestic polymer market. "
            "Collects, structures, and delivers market information to internal dashboard, "
            "Telegram Web App, and Telegram bot/channel."
        ),
        docs_url=_docs_url,
        redoc_url=_redoc_url,
        openapi_url=_openapi_url,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # CR-04 / T-03-05: origins come from settings.CORS_ALLOWED_ORIGINS (an explicit
    # non-wildcard list). Wildcard allow_origins with allow_credentials=True is both
    # a security misconfiguration and non-functional per the CORS spec — browsers
    # reject credentialed responses when the server returns Access-Control-Allow-Origin: *.
    # Set CORS_ALLOWED_ORIGINS in your .env to control which origins may send
    # credentialed (cookie-bearing) requests; e.g.:
    #   CORS_ALLOWED_ORIGINS=http://localhost:3000,https://dashboard.example.com
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Telegram-Init-Data"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # All API routes are mounted under /api/v1 per dev-spec §3.2.
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(admin_sources_router, prefix="/api/v1")
    # ── dashboard routers (Phase 4 internal team dashboard) ──────────────────
    application.include_router(feed_router, prefix="/api/v1")
    # ── webapp routers (Telegram Web App client surface) ─────────────────────
    application.include_router(webapp_requests_router, prefix="/api/v1")
    application.include_router(webapp_me_router, prefix="/api/v1")
    application.include_router(webapp_files_router, prefix="/api/v1")
    # ── telegram bot webhook (dev-spec §4.1: webhook inside api container) ────
    application.include_router(telegram_webhook_router, prefix="/api/v1")

    # ── Demo guard routes (REQ-roles testable hooks) ───────────────────────────
    # These minimal routes exist to prove the require_role guard works end-to-end.
    # The full /admin/users CRUD ships in Phase 4 (admin management screen).
    # The full /analyst/* data endpoints ship in Phase 2+.

    @application.get("/api/v1/admin/whoami", tags=["admin-demo"])
    def admin_whoami(
        current_user: StaffUser = Depends(require_admin),
    ) -> dict:
        """Admin-only demo route. Returns 403 for non-admin roles (REQ-roles guard test)."""
        return {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role.value,
        }

    @application.get("/api/v1/analyst/whoami", tags=["analyst-demo"])
    def analyst_whoami(
        current_user: StaffUser = Depends(require_analyst_or_admin),
    ) -> dict:
        """Analyst+admin demo route. Returns 403 for trader/viewer (REQ-roles guard test)."""
        return {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role.value,
        }

    return application


# Module-level app instance for uvicorn.
# e.g.: uvicorn app.main:app
app = create_app()
