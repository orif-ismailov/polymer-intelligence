"""
GET /health — dependency health check endpoint.

Returns HTTP 200 with a JSON body reporting db, redis, and schema status.
Always returns 200 (even if a dependency is degraded) so monitoring systems
can read the per-component status without treating 5xx as an alert.

Response schema:
    {
        "status": "ok" | "degraded",
        "db": "ok" | "error",
        "redis": "ok" | "error",
        "schema_version": "0001" | null   -- alembic revision, null if not migrated
    }

Security (T-01-02 / T-02-03): Only status enums and the alembic revision string
are returned — no connection strings, sensitive config, or stack traces.
The revision string is low-value information (T-02-03 accepted).

REQ-nfr-observability: health check enables uptime monitoring per §3.2;
schema_version proves migrations have been applied (plan 01-02 requirement).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


StatusValue = Literal["ok", "error"]
OverallStatus = Literal["ok", "degraded"]


class HealthResponse(BaseModel):
    status: OverallStatus
    db: StatusValue
    redis: StatusValue
    schema_version: str | None = None


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


def _get_schema_version(db: Session) -> str | None:
    """Query alembic_version for the current revision.

    Returns the revision string (e.g., '0001'), or None if the table does not
    exist yet (unmigrated database) or on any error.

    REQ-nfr-observability: proves schema has been applied (T-02-03 accepted risk).
    """
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        row = result.fetchone()
        if row is None:
            return None
        # Ensure we return a plain string, not a MagicMock or other object in tests
        value = row[0]
        if isinstance(value, str):
            return value
        return None
    except Exception as exc:
        # alembic_version table may not exist on an unmigrated DB
        logger.debug("health.schema_version_unavailable", exc_info=exc)
        return None


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Check Postgres, Redis connectivity, and schema migration status.

    Returns 200 in all cases; inspect `db` and `redis` fields for per-component
    status.  `status` is 'ok' only if both dependencies are healthy.
    `schema_version` is the current alembic revision, or null if not migrated.
    """
    db_status = _check_db(db)
    redis_status = _check_redis()
    schema_version = _get_schema_version(db)
    overall: OverallStatus = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        db=db_status,
        redis=redis_status,
        schema_version=schema_version,
    )
