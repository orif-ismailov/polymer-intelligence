"""
llm_page_fetch — Celery task: fetch enabled llm_page sources and enqueue LLM extraction.

For each enabled source with adapter='llm_page', fetch the page via
LlmPageAdapter (SSRF-guarded), persist the page text as an immutable raw_item,
and enqueue ``parse_telegram_item`` — the generic content→signal LLM extractor —
for each newly inserted raw_item.

Reuses the per-source isolation helper (run_source_fetch_isolated) so a failure
in one source cannot abort the batch or affect siblings (T-02-17), with the parse
task routed to ``parse_telegram_item`` instead of the UZEX rule parser.

Beat schedule (schedule.py): 'llm_page_fetch' at crontab(minute=30)  → hourly.
Queue: 'ingest'.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="llm_page_fetch")  # type: ignore[untyped-decorator]
def llm_page_fetch() -> dict[str, Any]:
    """Fetch all enabled llm_page sources and enqueue LLM extraction per new item.

    Returns:
        Dict with keys: status, adapter, sources_processed, total_inserted, errors.
    """
    import app.ingest.llm_page  # noqa: F401, PLC0415 — triggers adapter self-registration
    from app.core.db import engine  # noqa: PLC0415
    from app.ingest.registry import get_adapter  # noqa: PLC0415
    from app.tasks.ingest import (  # noqa: PLC0415
        _load_enabled_sources,
        run_source_fetch_isolated,
    )

    logger.info("llm_page_fetch.start")
    adapter = get_adapter("llm_page")

    sources_processed = 0
    total_inserted = 0

    with Session(engine) as session:
        sources = _load_enabled_sources(session, "llm_page")

        if not sources:
            logger.info("llm_page_fetch.no_enabled_sources")
            return {
                "status": "ok",
                "adapter": "llm_page",
                "sources_processed": 0,
                "total_inserted": 0,
                "errors": [],
            }

        for source in sources:
            # Per-source isolation + health recording; enqueues the LLM extractor
            # (parse_telegram_item) for each newly inserted raw_item.
            inserted = run_source_fetch_isolated(
                session, source, adapter, parse_task_name="parse_telegram_item"
            )
            total_inserted += inserted
            sources_processed += 1

    logger.info(
        "llm_page_fetch.done",
        extra={"sources": sources_processed, "inserted": total_inserted},
    )
    return {
        "status": "ok",
        "adapter": "llm_page",
        "sources_processed": sources_processed,
        "total_inserted": total_inserted,
        "errors": [],
    }
