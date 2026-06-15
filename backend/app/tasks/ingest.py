"""
UZEX fetch Celery tasks — replaces placeholders from 02-01.

Registers the real `uzex_fetch_offers`, `uzex_fetch_contracts`, and
`uzex_fetch_deals` tasks that supersede the placeholders in
tasks/placeholders.py (same task names; last registration wins during
autodiscovery — Celery resolves by name, not by module).

Beat schedule (from 02-01/schedule.py):
    uzex_fetch_offers    — crontab(minute="*/15", hour="9-18", day_of_week="mon-fri")
    uzex_fetch_contracts — crontab(minute=0)
    uzex_fetch_deals     — crontab(minute=0)

Workflow per task:
1. Load all enabled Source rows for this adapter type.
2. For each source, call the adapter's fetch() via asyncio.run().
3. Persist returned RawItemDraft list via save_raw_items (dedup + immutable).
4. Update source.last_fetch_at.
5. Enqueue parse_raw_item for each newly inserted raw_item ID.

Per-source exception handling:
- A failure in one source's fetch/save does NOT abort the batch.
- The exception is logged and re-raised at source level only.
- Alert/health escalation (3-failure threshold) is layered in 02-06.

Security:
  T-02-11: Row/cell caps enforced in parse_table_rows (upstream).
  T-02-12: All DB writes via bound parameters (raw_pipeline / ORM).
  T-02-17: Per-source try/except isolates failures; one source cannot kill others.
  T-02-18: last_fetch_at tracks fetch traceability at source level.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import sqlalchemy as sa

from app.services.raw_pipeline import save_raw_items
from app.services.source_health_service import record_fetch_failure, record_fetch_success
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_enabled_sources(session: Any, adapter_name: str) -> list[Any]:
    """Load all enabled Source rows for a given adapter type."""
    from app.models.sources import Source  # noqa: PLC0415

    result: list[Any] = (
        session.query(Source)
        .filter(
            sa.text("adapter = :adapter AND is_enabled = true"),
        )
        .params(adapter=adapter_name)
        .all()
    )
    return result


def _run_fetch_for_source(adapter: Any, source: Any) -> list[Any]:
    """Run the async adapter.fetch() from the synchronous Celery task context."""
    return asyncio.run(adapter.fetch(source))


def run_source_fetch_isolated(session: Any, source: Any, adapter: Any) -> int:
    """Fetch a single source's data with full failure isolation and health recording.

    Wraps the per-source fetch + save in try/except so that a failure in one
    source cannot abort the batch or affect sibling sources (SC#5 / T-02-17 /
    T-02-19 / REQ-nfr-reliability).

    On success:
      - Persists returned drafts via save_raw_items (dedup + immutable).
      - Calls record_fetch_success (sets last_fetch_at, last_success_at, resets counter).
      - Enqueues parse_raw_item for each newly inserted raw_item.

    On any exception:
      - Logs the error structured.
      - Calls record_fetch_failure (increments counter, raises alert at 3 strikes).
      - Rolls back the session to leave it usable for the next source.
      - NEVER re-raises — the exception is fully contained here.

    Args:
        session: Active SQLAlchemy session.
        source: Source ORM object (or row-like) with .id and adapter fields.
        adapter: SourceAdapter instance whose fetch() is called.

    Returns:
        The number of raw_items inserted (0 on failure or no new items).
    """
    try:
        drafts = _run_fetch_for_source(adapter, source)
        logger.info(
            "uzex_fetch.fetched",
            extra={
                "source_id": source.id,
                "drafts": len(drafts),
            },
        )

        inserted = save_raw_items(session, source, drafts)
        session.commit()

        record_fetch_success(session, source.id)
        session.commit()

        if inserted > 0:
            _enqueue_parse_tasks(session, source.id, inserted)

        return inserted

    except Exception as exc:
        # Per-source isolation: log, record failure, DO NOT re-raise (T-02-17, T-02-19)
        logger.error(
            "uzex_fetch.source_error",
            extra={"source_id": source.id, "error": str(exc)},
        )
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            session.rollback()

        record_fetch_failure(session, source.id, str(exc))
        with contextlib.suppress(Exception):
            session.commit()

        return 0


def _execute_uzex_fetch(adapter_name: str) -> dict[str, Any]:
    """Shared implementation for all three UZEX fetch tasks.

    Args:
        adapter_name: Registry key of the adapter (e.g. 'uzex_offers').

    Returns:
        Dict with keys: status, adapter, sources_processed, total_inserted, errors.
    """
    import app.ingest.uzex  # noqa: F401, PLC0415 — triggers adapter self-registration  # isort: skip
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter(adapter_name)

    sources_processed = 0
    total_inserted = 0

    with Session(engine) as session:
        sources = _load_enabled_sources(session, adapter_name)

        if not sources:
            logger.info(
                "uzex_fetch.no_enabled_sources",
                extra={"adapter": adapter_name},
            )
            return {
                "status": "ok",
                "adapter": adapter_name,
                "sources_processed": 0,
                "total_inserted": 0,
                "errors": [],
            }

        for source in sources:
            # ── Per-source fetch with failure isolation and health recording ──
            # run_source_fetch_isolated catches all exceptions, records success/failure,
            # and never re-raises so sibling sources keep running (SC#5 / T-02-17 / T-02-19)
            inserted = run_source_fetch_isolated(session, source, adapter)
            total_inserted += inserted
            sources_processed += 1

    logger.info(
        "uzex_fetch.done",
        extra={
            "adapter": adapter_name,
            "sources": sources_processed,
            "inserted": total_inserted,
        },
    )
    return {
        "status": "ok",
        "adapter": adapter_name,
        "sources_processed": sources_processed,
        "total_inserted": total_inserted,
        "errors": [],
    }


def _enqueue_parse_tasks(session: Any, source_id: int, count: int) -> None:
    """Enqueue parse_raw_item tasks for the most recently inserted rows.

    Queries raw_items for the latest `count` pending rows for this source
    and sends a parse_raw_item task for each.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT id FROM raw_items
            WHERE source_id = :sid AND parse_status = 'pending'
            ORDER BY fetched_at DESC
            LIMIT :lim
            """
        ),
        {"sid": source_id, "lim": count},
    ).fetchall()

    for row in rows:
        celery_app.send_task("parse_raw_item", args=[row[0]], queue="parse")

    logger.debug(
        "uzex_fetch.enqueue_parse",
        extra={"source_id": source_id, "enqueued": len(rows)},
    )


# ── Celery tasks ──────────────────────────────────────────────────────────────


@celery_app.task(name="uzex_fetch_offers")  # type: ignore[untyped-decorator]
def uzex_fetch_offers() -> dict[str, Any]:
    """Fetch UZEX open auction offers (sum/currency/import sections).

    Supersedes the placeholder in tasks/placeholders.py.
    Scheduled by beat: every 15 min, 09:00-18:00, Mon-Fri (Asia/Tashkent).
    """
    logger.info("uzex_fetch_offers.start")
    return _execute_uzex_fetch("uzex_offers")


@celery_app.task(name="uzex_fetch_contracts")  # type: ignore[untyped-decorator]
def uzex_fetch_contracts() -> dict[str, Any]:
    """Fetch UZEX active quotation/contract listings (sum/currency sections).

    Supersedes the placeholder in tasks/placeholders.py.
    Scheduled by beat: every hour.
    """
    logger.info("uzex_fetch_contracts.start")
    return _execute_uzex_fetch("uzex_contracts")


@celery_app.task(name="uzex_fetch_deals")  # type: ignore[untyped-decorator]
def uzex_fetch_deals() -> dict[str, Any]:
    """Fetch the UZEX concluded-deal registry (/Trade/List).

    Supersedes the placeholder in tasks/placeholders.py.
    Scheduled by beat: every hour.
    """
    logger.info("uzex_fetch_deals.start")
    return _execute_uzex_fetch("uzex_deals")
