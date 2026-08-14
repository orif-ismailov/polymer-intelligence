"""
Userbot heartbeat health service.

Checks whether the Telegram userbot process is alive by reading its Redis
heartbeat key. Raises a deduped source_failure admin alert when the heartbeat
is absent or stale by more than USERBOT_SILENCE_SECONDS (300 s = 5 min).

This is the monitoring path for ROADMAP SC#1:
  "silence >5 min alerts"

The alert is inserted with ON CONFLICT (dedupe_key) DO NOTHING so that at most
one alert per UTC calendar day is produced, no matter how many times the health
task runs (T-05-08 / T-02-20 defense-in-depth pattern, mirroring source_health_service).

Functions:
- check_userbot_heartbeat(session, redis): read heartbeat; insert alert if stale.

Security:
  T-05-08: Redis heartbeat + this health check + deduped alert is the liveness
           tripwire. If the userbot process dies without restarting (e.g. OOM
           kill), the alert surfaces within 5 min (the check_source_health beat).
"""

from __future__ import annotations

import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# How long the userbot can be silent before an admin alert is raised (seconds).
# Aligned with the check cadence: the */5 beat checks every 5 min; a 5-min
# silence threshold means the first missed heartbeat triggers the alert.
USERBOT_SILENCE_SECONDS = 300


def check_userbot_heartbeat(session: Session, redis: object) -> None:
    """Check the userbot heartbeat and raise a deduped alert if stale.

    Reads ``userbot:heartbeat`` from Redis. If the key is absent or older than
    USERBOT_SILENCE_SECONDS, inserts a source_failure alert with dedupe_key
    ``userbot_silent:{utc_date}`` using ON CONFLICT (dedupe_key) DO NOTHING.

    This mirrors the raise_source_failure_alert dedupe idiom from
    source_health_service.py (T-02-20 / T-05-08).

    Args:
        session: Active SQLAlchemy session. Calls flush(); caller commits.
        redis: A redis.Redis client (or any compatible mock).
    """
    from userbot.heartbeat import read_heartbeat  # noqa: PLC0415

    ts = read_heartbeat(redis)
    now = datetime.datetime.now(tz=datetime.UTC)
    now_epoch = now.timestamp()

    if ts is None:
        stale = True
        age_seconds: float = float("inf")
        reason = "heartbeat_absent"
    else:
        age_seconds = now_epoch - ts
        stale = age_seconds > USERBOT_SILENCE_SECONDS
        reason = f"heartbeat_stale_{int(age_seconds)}s" if stale else "heartbeat_ok"

    if not stale:
        logger.debug(
            "userbot_health.heartbeat_ok",
            extra={"age_seconds": age_seconds},
        )
        return

    # Insert a deduped alert (at most one per UTC calendar day)
    today = now.date().isoformat()
    dedupe_key = f"userbot_silent:{today}"

    session.execute(
        sa.text(
            """
            INSERT INTO alerts (kind, severity, title, body, dedupe_key)
            VALUES (
                'source_failure',
                'warning',
                :title,
                :body,
                :dedupe_key
            )
            ON CONFLICT (dedupe_key) DO NOTHING
            """
        ),
        {
            "title": "Userbot silent >5 min",
            "body": (
                f"The Telegram userbot process has not written a heartbeat for "
                f"more than {USERBOT_SILENCE_SECONDS}s (reason: {reason}). "
                f"Check the userbot container logs and restart if necessary. "
                f"ROADMAP SC#1 monitoring is disrupted until the userbot reconnects."
            ),
            "dedupe_key": dedupe_key,
        },
    )
    session.flush()

    logger.warning(
        "userbot_health.alert_raised",
        extra={
            "dedupe_key": dedupe_key,
            "reason": reason,
            "age_seconds": age_seconds if ts is not None else None,
        },
    )
