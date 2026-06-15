"""
Source health bookkeeping service.

Tracks per-source fetch success/failure state and raises deduped source_failure
alerts when a source exceeds the 3-consecutive-failure threshold.

Functions:
- record_fetch_success(session, source_id): sets last_fetch_at + last_success_at = now,
  consecutive_failures = 0.
- record_fetch_failure(session, source_id, error): increments consecutive_failures, sets
  last_fetch_at = now; if the new count >= 3 calls raise_source_failure_alert.
  Returns the new consecutive_failures count.
- raise_source_failure_alert(session, source_id): inserts ONE alert with
  dedupe_key = "source_failure:{source_id}:{date.today().isoformat()}"
  and ON CONFLICT (dedupe_key) DO NOTHING — guarantees at most one alert per source per day.
- check_all_sources_health(session): scans all enabled sources with
  consecutive_failures >= 3 and calls raise_source_failure_alert for each.
  Idempotent: safe to call on the */5 beat regardless of prior inline raises.

Security:
  T-02-19: Failure isolation — the caller (ingest task) must NOT re-raise; this service
           just records and dedupes the alert.
  T-02-20: dedupe_key source_failure:{source_id}:{date} + UNIQUE(dedupe_key)
           ON CONFLICT DO NOTHING → at most one alert per source per day (no alert storm).
  T-02-22: check_all_sources_health independently guarantees the alert within ≤30 min
           even if the inline raise path was missed.

Style:
  Uses db.flush() inside raise_source_failure_alert; the caller is responsible for
  committing the transaction (pattern from audit_service.py).
"""

from __future__ import annotations

import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Threshold for raising a source_failure alert
_FAILURE_THRESHOLD = 3


def record_fetch_success(session: Session, source_id: int) -> None:
    """Record a successful fetch for a source.

    Sets last_fetch_at = now(), last_success_at = now(), and
    consecutive_failures = 0.

    Args:
        session: Active SQLAlchemy session (caller commits).
        source_id: The id of the source that succeeded.
    """
    now = datetime.datetime.now(tz=datetime.UTC)
    session.execute(
        sa.text(
            """
            UPDATE sources
            SET last_fetch_at = :now,
                last_success_at = :now,
                consecutive_failures = 0
            WHERE id = :id
            """
        ),
        {"now": now, "id": source_id},
    )
    logger.debug(
        "source_health.fetch_success",
        extra={"source_id": source_id},
    )


def record_fetch_failure(
    session: Session,
    source_id: int,
    error: str,
) -> int:
    """Record a failed fetch for a source.

    Increments consecutive_failures by 1, sets last_fetch_at = now().
    If the new consecutive_failures >= 3, calls raise_source_failure_alert
    to insert a deduped alert.

    Args:
        session: Active SQLAlchemy session (caller commits).
        source_id: The id of the source that failed.
        error: The error message / exception string (structured-logged).

    Returns:
        The new consecutive_failures count after incrementing.
    """
    now = datetime.datetime.now(tz=datetime.UTC)

    # Increment consecutive_failures and return the new value
    row = session.execute(
        sa.text(
            """
            UPDATE sources
            SET last_fetch_at = :now,
                consecutive_failures = consecutive_failures + 1
            WHERE id = :id
            RETURNING consecutive_failures
            """
        ),
        {"now": now, "id": source_id},
    ).fetchone()

    if row is None:
        logger.error(
            "source_health.source_not_found",
            extra={"source_id": source_id, "error": error},
        )
        return 0

    new_count: int = int(row[0])

    logger.info(
        "source_health.fetch_failure",
        extra={
            "source_id": source_id,
            "consecutive_failures": new_count,
            "error": error,
        },
    )

    # Trigger the 3-strike alert
    if new_count >= _FAILURE_THRESHOLD:
        raise_source_failure_alert(session, source_id)

    return new_count


def raise_source_failure_alert(session: Session, source_id: int) -> None:
    """Insert a source_failure alert (deduped per source per day).

    Uses dedupe_key = "source_failure:{source_id}:{YYYY-MM-DD}" with
    ON CONFLICT (dedupe_key) DO NOTHING to guarantee at most one alert
    per source per calendar day, even if called concurrently (T-02-20).

    Args:
        session: Active SQLAlchemy session. Calls flush() — caller commits.
        source_id: The id of the failing source.
    """
    today = datetime.date.today().isoformat()
    dedupe_key = f"source_failure:{source_id}:{today}"

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
            "title": f"Source {source_id} — 3 consecutive fetch failures",
            "body": (
                f"Source id={source_id} has reached {_FAILURE_THRESHOLD} consecutive "
                f"fetch failures. Check the source configuration and collector logs."
            ),
            "dedupe_key": dedupe_key,
        },
    )
    session.flush()

    logger.warning(
        "source_health.alert_raised",
        extra={"source_id": source_id, "dedupe_key": dedupe_key},
    )


def check_all_sources_health(session: Session) -> None:
    """Scan all enabled sources and raise alerts for those with consecutive_failures >= 3.

    This is the */5 safety net: it guarantees the deduped source_failure alert
    exists within 30 minutes even if the inline raise inside record_fetch_failure
    was missed (T-02-22, defense in depth).

    Idempotent: can be called any number of times — raise_source_failure_alert uses
    ON CONFLICT DO NOTHING so duplicate alert rows are never created.

    Args:
        session: Active SQLAlchemy session (caller commits).
    """
    rows = session.execute(
        sa.text(
            """
            SELECT id FROM sources
            WHERE is_enabled = true
              AND consecutive_failures >= :threshold
            """
        ),
        {"threshold": _FAILURE_THRESHOLD},
    ).fetchall()

    for row in rows:
        source_id = int(row[0])
        raise_source_failure_alert(session, source_id)

    if rows:
        logger.info(
            "source_health.scan_complete",
            extra={"sources_checked": len(rows)},
        )
