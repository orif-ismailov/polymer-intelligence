"""
News-engine Celery tasks (Phase 3).

generate_daily_report builds today's market report as a draft (human-in-the-loop:
staff approve → publish on the dashboard). Scheduled by beat; see app/tasks/schedule.py.
"""

from __future__ import annotations

import logging

from app.core.db import SessionLocal
from app.services import report_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_daily_report")
def generate_daily_report() -> int | None:
    """Generate today's report (draft). Returns the new report id, or None on failure."""
    with SessionLocal() as db:
        try:
            report = report_service.generate_report(db)
            db.commit()
            logger.info("generate_daily_report.done", extra={"report_id": report.id})
            return report.id
        except Exception:
            logger.exception("generate_daily_report.failed")
            db.rollback()
            return None
