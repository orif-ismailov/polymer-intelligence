"""
Source health check Celery task — replaces 02-01 placeholder.

Registers the real `check_source_health` Celery task that supersedes the
placeholder in tasks/placeholders.py (same task name; last registration wins
during autodiscovery — Celery resolves by name, not by module).

Beat schedule (from app.tasks.schedule):
    check_source_health — crontab(minute="*/5")  → every 5 minutes

This task provides the ≤30 min guarantee for the 3-strike deduped source_failure
alert (T-02-22): even if the inline raise inside record_fetch_failure was missed
for any reason, this scan finds any enabled source with consecutive_failures >= 3
and calls raise_source_failure_alert idempotently.

Security:
  T-02-20: alert deduplication via source_health_service.raise_source_failure_alert
           (ON CONFLICT DO NOTHING on dedupe_key) — no alert storm.
  T-02-22: defense in depth for the ≤30 min guarantee (independent scan).
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="check_source_health")  # type: ignore[untyped-decorator]
def check_source_health() -> dict[str, Any]:
    """Scan all enabled sources and raise deduped source_failure alerts for any with >= 3 failures.

    Supersedes the placeholder in tasks/placeholders.py.
    Scheduled by beat: every 5 minutes.

    This is the safety net for REQ-nfr-reliability SC#5:
    - Guarantees that a source_failure alert is visible within 30 minutes
      even if the inline raise inside record_fetch_failure was missed.
    - Idempotent: safe to run repeatedly; alerts are deduped per source per day.

    Returns:
        A dict with keys: status, scanned_count (int), error (str | None)
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.services.source_health_service import check_all_sources_health  # noqa: PLC0415

    logger.info("check_source_health.start")

    try:
        with Session(engine) as session:
            check_all_sources_health(session)
            session.commit()
    except Exception as exc:
        logger.error("check_source_health.error", extra={"error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("check_source_health.done")
    return {"status": "ok", "error": None}
