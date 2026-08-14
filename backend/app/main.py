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

# ── Adapter registration (Phase 4, Plan 06) ──────────────────────────────────
# These imports self-register the source adapters into the global registry at
# startup so GET /admin/source-types exposes their config_schema and POST
# /sources/{id}/test can resolve them by type_name. Both the no-code adapters
# (html_table/llm_page/rss/telegram_channel, added via the source constructor) AND
# the built-in code adapters for seeded sources (uzex_*, cbu_rates) must be
# registered in the API process — the worker registers its own set in
# app.tasks.ingest, so without these the dashboard "Test" button on a UZEX/CBU
# source returns "No adapter registered for type '...'".
import app.ingest.cbu_rates  # noqa: E402, F401 — registers cbu_rates adapter
import app.ingest.html_table  # noqa: E402, F401 — registers html_table adapter
import app.ingest.llm_page  # noqa: E402, F401 — registers llm_page adapter
import app.ingest.rss  # noqa: E402, F401 — registers rss adapter
import app.ingest.telegram_channel  # noqa: E402, F401 — registers telegram_channel adapter
import app.ingest.uzex  # noqa: E402, F401 — registers uzex_offers/contracts/deals adapters
import app.ingest.xarid  # noqa: E402, F401 — registers xarid_tenders adapter
from app.api.admin_products import router as admin_products_router
from app.api.admin_settings import router as admin_settings_router
from app.api.admin_sources import router as admin_sources_router
from app.api.admin_users import router as admin_users_router
from app.api.alert_rules import alerts_router
from app.api.alert_rules import router as alert_rules_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.dashboard_requests import router as dashboard_requests_router
from app.api.deps import require_admin, require_analyst_or_admin
from app.api.feed import router as feed_router
from app.api.health import router as health_router
from app.api.portal.auth import router as portal_auth_router
from app.api.portal.notifications import router as portal_notifications_router
from app.api.portal.reference import router as portal_reference_router
from app.api.portal.requests import router as portal_requests_router
from app.api.public import router as public_router
from app.api.sources import router as sources_router
from app.api.sourcing import router as sourcing_router
from app.api.telegram_webhook import router as telegram_webhook_router
from app.api.webapp.auth import router as webapp_auth_router
from app.api.webapp.files import router as webapp_files_router
from app.api.webapp.me import router as webapp_me_router
from app.api.webapp.reference import router as webapp_reference_router
from app.api.webapp.requests import router as webapp_requests_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.domains.companies.api_portal import router as portal_companies_router
from app.domains.compliance.api_admin_licenses import router as admin_licenses_router
from app.domains.compliance.api_admin_substances import router as admin_substances_router
from app.domains.compliance.api_portal import router as portal_compliance_router
from app.domains.compliance.api_portal_substances import router as portal_substances_router
from app.domains.contracts.api_admin import router as admin_contracts_router
from app.domains.contracts.api_portal import router as portal_contracts_router
from app.domains.contracts.api_portal_eimzo import router as portal_eimzo_router
from app.domains.deals.api_admin import router as admin_deals_router
from app.domains.deals.api_admin_escrow import router as admin_escrow_router
from app.domains.deals.api_portal import router as portal_deals_router
from app.domains.deals.api_webhooks import router as webhooks_escrow_router
from app.domains.lab_orders.api_admin import router as admin_lab_router
from app.domains.lab_orders.api_portal import router as portal_lab_router
from app.domains.lab_orders.api_portal_samples import router as portal_samples_router
from app.domains.laboratory.api_admin import router as admin_lab_requests_router
from app.domains.laboratory.api_portal import router as portal_lab_requests_router
from app.domains.logistics.api_admin import router as admin_logistics_requests_router
from app.domains.logistics.api_portal import router as portal_logistics_router
from app.domains.manufacturers.api_portal import router as portal_manufacturers_router
from app.domains.marketplace.api_admin import router as offer_requests_router
from app.domains.marketplace.api_admin_moderation import router as moderation_router
from app.domains.marketplace.api_portal import router as portal_offers_router
from app.domains.marketplace.api_portal_inquiries import router as portal_inquiries_router
from app.domains.marketplace.api_portal_market import router as portal_market_router
from app.domains.marketplace.api_webapp_market import router as webapp_market_router
from app.domains.marketplace.api_webapp_seller import router as webapp_seller_router
from app.domains.news.api_admin import router as reports_router
from app.domains.news.api_portal import router as portal_news_router
from app.domains.news.api_webapp import router as webapp_news_router
from app.domains.pricing.api_admin import router as prices_router
from app.domains.verification.api_admin import router as admin_verification_router
from app.domains.verification.api_portal import router as portal_verification_router
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
    # Best-effort: a missing/placeholder BOT_TOKEN or a transient Telegram API error
    # must NOT stop the API from serving the dashboard/web app. Log and continue.
    if settings.PUBLIC_WEBAPP_URL:
        try:
            from telegram.bot import setup_webhook  # noqa: PLC0415

            await setup_webhook()
            logger.info("lifespan.telegram_webhook_registered")
        except Exception:
            logger.exception("lifespan.telegram_webhook_failed")

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
    # ── public marketplace storefront (anonymous — server-rendered for search) ─
    # Deliberately first among the product routers: it is the only surface with
    # no auth dependency, so it stays visible at the top rather than buried in
    # the portal block where a reader would assume the account guard applies.
    application.include_router(public_router, prefix="/api/v1")
    # ── dashboard routers (Phase 4 internal team dashboard) ──────────────────
    application.include_router(feed_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(dashboard_requests_router, prefix="/api/v1")
    application.include_router(admin_users_router, prefix="/api/v1")
    application.include_router(admin_products_router, prefix="/api/v1")
    application.include_router(admin_settings_router, prefix="/api/v1")
    # ── sources wizard router (Phase 4, Plan 06 — no-code source constructor) ─
    application.include_router(sources_router, prefix="/api/v1")
    # ── alerts engine routers (Phase 4, Plan 07 — alert rules CRUD + alerts feed) ─
    application.include_router(alert_rules_router, prefix="/api/v1")
    application.include_router(alerts_router, prefix="/api/v1")
    # ── prices router (Phase 4, Plan 07 — price series endpoint) ─────────────
    application.include_router(prices_router, prefix="/api/v1")
    # ── webapp routers (Telegram Web App client surface) ─────────────────────
    application.include_router(webapp_auth_router, prefix="/api/v1")
    application.include_router(webapp_requests_router, prefix="/api/v1")
    application.include_router(webapp_me_router, prefix="/api/v1")
    application.include_router(webapp_files_router, prefix="/api/v1")
    # ── marketplace (Phase 2): seller offers + public catalog + moderation ───
    application.include_router(webapp_seller_router, prefix="/api/v1")
    application.include_router(webapp_market_router, prefix="/api/v1")
    application.include_router(webapp_reference_router, prefix="/api/v1")
    application.include_router(moderation_router, prefix="/api/v1")
    application.include_router(offer_requests_router, prefix="/api/v1")
    # ── news engine (Phase 3): published reports + dashboard review ───────────
    application.include_router(webapp_news_router, prefix="/api/v1")
    application.include_router(reports_router, prefix="/api/v1")
    # ── AI broker dashboard (Phase 4): inventory/partners/sourcing/intel ─────
    application.include_router(sourcing_router, prefix="/api/v1")
    # ── telegram bot webhook (dev-spec §4.1: webhook inside api container) ────
    application.include_router(telegram_webhook_router, prefix="/api/v1")
    # External provider callback inbox (R6 / P7.b) — authenticated by a shared
    # secret, not a JWT; absent from the OpenAPI schema.
    application.include_router(webhooks_escrow_router, prefix="/api/v1")
    # ── portal (client cabinet — passwordless OTP accounts, R1 W3) ─────────────
    application.include_router(portal_auth_router, prefix="/api/v1")
    application.include_router(portal_contracts_router, prefix="/api/v1")
    # Deals before companies: its literal /portal/companies/{company_id}/deals routes
    # must be matched by this router rather than falling into the companies router's
    # /{company_id} param route.
    application.include_router(portal_deals_router, prefix="/api/v1")
    application.include_router(portal_compliance_router, prefix="/api/v1")
    # Lab orders hang off /portal/companies/{id}/lab-orders — same reason again.
    application.include_router(portal_lab_router, prefix="/api/v1")
    application.include_router(portal_samples_router, prefix="/api/v1")
    application.include_router(portal_companies_router, prefix="/api/v1")
    # Applicant-side verification, split out of the companies router (P2). Its paths
    # all sit one segment below /portal/companies/{company_id}, so they can neither
    # shadow nor be shadowed by that param route — position here is not load-bearing.
    application.include_router(portal_verification_router, prefix="/api/v1")
    application.include_router(portal_eimzo_router, prefix="/api/v1")
    application.include_router(portal_offers_router, prefix="/api/v1")
    application.include_router(portal_market_router, prefix="/api/v1")
    # Manufacturers before any catch-all company/id routes that could shadow list paths.
    application.include_router(portal_manufacturers_router, prefix="/api/v1")
    # `/portal/logistics` collides with nothing under `/portal/companies`, so
    # registration order against that router does not matter here.
    application.include_router(portal_logistics_router, prefix="/api/v1")
    application.include_router(portal_lab_requests_router, prefix="/api/v1")
    application.include_router(portal_substances_router, prefix="/api/v1")
    application.include_router(portal_reference_router, prefix="/api/v1")
    application.include_router(portal_inquiries_router, prefix="/api/v1")
    application.include_router(portal_requests_router, prefix="/api/v1")
    application.include_router(portal_news_router, prefix="/api/v1")
    application.include_router(portal_notifications_router, prefix="/api/v1")
    application.include_router(admin_verification_router, prefix="/api/v1")
    application.include_router(admin_contracts_router, prefix="/api/v1")
    application.include_router(admin_deals_router, prefix="/api/v1")
    application.include_router(admin_escrow_router, prefix="/api/v1")
    application.include_router(admin_substances_router, prefix="/api/v1")
    application.include_router(admin_licenses_router, prefix="/api/v1")
    application.include_router(admin_lab_router, prefix="/api/v1")
    application.include_router(admin_logistics_requests_router, prefix="/api/v1")
    application.include_router(admin_lab_requests_router, prefix="/api/v1")

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
