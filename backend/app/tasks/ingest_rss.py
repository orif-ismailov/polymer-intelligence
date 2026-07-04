"""
rss_fetch — Celery task: fetch enabled rss sources into raw_items.

For each enabled source with adapter='rss', fetch the feed via RssAdapter
(SSRF-guarded), persist each entry as an immutable raw_item, and enqueue
``parse_telegram_item`` — the generic content→signal LLM extractor — for each
newly inserted raw_item. RSS entries are unstructured headline/summary text
(no mapped price/volume), so LLM extraction is the right path, identical to how
Telegram messages and llm_page pages are processed.

Reuses the per-source isolation helper (run_source_fetch_isolated) so a failure
in one source cannot abort the batch or affect siblings (T-02-17).

Beat schedule (schedule.py): 'rss_fetch' at crontab(minute=45) → hourly.
Queue: 'ingest'.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="rss_fetch")  # type: ignore[untyped-decorator]
def rss_fetch() -> dict[str, Any]:
    """Fetch all enabled rss sources and enqueue LLM extraction per new item.

    Returns:
        Dict with keys: status, adapter, sources_processed, total_inserted, errors.
    """
    import app.ingest.rss  # noqa: F401, PLC0415 — triggers adapter self-registration
    from app.core.db import engine  # noqa: PLC0415
    from app.ingest.registry import get_adapter  # noqa: PLC0415
    from app.tasks.ingest import (  # noqa: PLC0415
        _load_enabled_sources,
        run_source_fetch_isolated,
    )

    logger.info("rss_fetch.start")
    adapter = get_adapter("rss")

    sources_processed = 0
    total_inserted = 0

    with Session(engine) as session:
        sources = _load_enabled_sources(session, "rss")

        if not sources:
            logger.info("rss_fetch.no_enabled_sources")
            return {
                "status": "ok",
                "adapter": "rss",
                "sources_processed": 0,
                "total_inserted": 0,
                "errors": [],
            }

        for source in sources:
            inserted = run_source_fetch_isolated(
                session, source, adapter, parse_task_name="parse_telegram_item"
            )
            total_inserted += inserted
            sources_processed += 1

    logger.info(
        "rss_fetch.done",
        extra={"sources": sources_processed, "inserted": total_inserted},
    )
    return {
        "status": "ok",
        "adapter": "rss",
        "sources_processed": sources_processed,
        "total_inserted": total_inserted,
        "errors": [],
    }
