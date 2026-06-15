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
import datetime
import logging
from typing import Any

import sqlalchemy as sa

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
    from app.services.raw_pipeline import save_raw_items  # noqa: PLC0415

    adapter = get_adapter(adapter_name)
    now = datetime.datetime.now(tz=datetime.UTC)

    sources_processed = 0
    total_inserted = 0
    errors: list[str] = []

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
            try:
                # ── Fetch via adapter (async → sync bridge) ───────────────────
                drafts = _run_fetch_for_source(adapter, source)
                logger.info(
                    "uzex_fetch.fetched",
                    extra={
                        "adapter": adapter_name,
                        "source_id": source.id,
                        "drafts": len(drafts),
                    },
                )

                # ── Save raw items with sha256 dedup ──────────────────────────
                inserted = save_raw_items(session, source, drafts)
                session.commit()
                total_inserted += inserted

                # ── Update last_fetch_at ───────────────────────────────────────
                session.execute(
                    sa.text(
                        "UPDATE sources SET last_fetch_at = :now WHERE id = :id"
                    ),
                    {"now": now, "id": source.id},
                )
                session.commit()

                sources_processed += 1

                # ── Enqueue parse_raw_item for each new row ───────────────────
                if inserted > 0:
                    _enqueue_parse_tasks(session, source.id, inserted)

            except Exception as exc:
                # Per-source isolation: log and continue (T-02-17)
                # 3-failure escalation is in 02-06 (check_source_health).
                error_msg = f"source_id={source.id}: {exc}"
                errors.append(error_msg)
                logger.error(
                    "uzex_fetch.source_error",
                    extra={"adapter": adapter_name, "source_id": source.id, "error": str(exc)},
                )
                import contextlib  # noqa: PLC0415
                with contextlib.suppress(Exception):
                    session.rollback()

    status = "ok" if not errors else "partial_error"
    logger.info(
        "uzex_fetch.done",
        extra={
            "adapter": adapter_name,
            "sources": sources_processed,
            "inserted": total_inserted,
            "errors": len(errors),
        },
    )
    return {
        "status": status,
        "adapter": adapter_name,
        "sources_processed": sources_processed,
        "total_inserted": total_inserted,
        "errors": errors,
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
