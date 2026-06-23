"""
Celery beat task — userbot heartbeat health check.

Runs every 5 minutes (*/5 * * * *) on the `ingest` queue.
Checks the Redis heartbeat written by the userbot process and raises a deduped
admin alert when the userbot has been silent for more than USERBOT_SILENCE_SECONDS
(300 s = 5 min).

This is the monitoring tripwire for ROADMAP SC#1 liveness (T-05-08):
  "silence >5 min alerts admin"

Routing:
  check_userbot_health -> ingest queue (mirrors check_source_health routing pattern)
  Beat schedule entry: see app.tasks.schedule.BEAT_SCHEDULE
"""

from __future__ import annotations

import logging

import redis as redis_lib

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.userbot_health_service import check_userbot_heartbeat
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="check_userbot_health")  # type: ignore[misc]
def check_userbot_health() -> None:
    """Celery beat task: check userbot heartbeat and raise alert if stale.

    Opens a short-lived SessionLocal + Redis client, delegates to
    check_userbot_heartbeat(), then commits.

    Registered on the */5 beat (schedule.py BEAT_SCHEDULE).
    Routes to the ingest queue (celery_app.py task_routes).
    """
    _redis = redis_lib.from_url(settings.REDIS_URL)
    with SessionLocal() as session:
        check_userbot_heartbeat(session, _redis)
        session.commit()

    logger.debug("check_userbot_health.done")
