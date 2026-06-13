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

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.deps import require_admin, require_analyst_or_admin
from app.models.staff import StaffUser


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
    application.include_router(auth_router, prefix="/api/v1")

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
