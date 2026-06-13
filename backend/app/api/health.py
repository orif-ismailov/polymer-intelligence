"""
GET /health — dependency health check endpoint.

Returns HTTP 200 with a JSON body reporting db and redis status.
Always returns 200 (even if a dependency is degraded) so monitoring systems
can read the per-component status without treating 5xx as an alert.

Response schema:
    {
        "status": "ok" | "degraded",
        "db": "ok" | "error",
        "redis": "ok" | "error"
    }

Security (T-01-02): Only status enums are returned — no connection strings,
version info, or stack traces.  Error detail stays in server-side logs only.

REQ-nfr-observability: health check enables uptime monitoring per §3.2.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


StatusValue = Literal["ok", "error"]
OverallStatus = Literal["ok", "degraded"]


class HealthResponse(BaseModel):
    status: OverallStatus
    db: StatusValue
    redis: StatusValue


def _check_db(db: Session) -> StatusValue:
    """Probe Postgres by executing SELECT 1.  Returns 'ok' or 'error'."""
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.error("health.db_check_failed", exc_info=exc)
        return "error"


def _check_redis() -> StatusValue:
    """Probe Redis with PING.  Returns 'ok' or 'error'."""
    try:
        import redis as redis_lib  # noqa: PLC0415 — lazy import to support test overrides

        client = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        return "ok"
    except Exception as exc:
        logger.error("health.redis_check_failed", exc_info=exc)
        return "error"


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Check Postgres and Redis connectivity.

    Returns 200 in all cases; inspect `db` and `redis` fields for per-component
    status.  `status` is 'ok' only if both dependencies are healthy.
    """
    db_status = _check_db(db)
    redis_status = _check_redis()
    overall: OverallStatus = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, db=db_status, redis=redis_status)
