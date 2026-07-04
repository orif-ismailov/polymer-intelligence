"""
html_table_fetch — Celery task: fetch enabled html_table sources into raw_items.

For each enabled source with adapter='html_table', fetch the target page via
HtmlTableAdapter (SSRF-guarded), persist each parsed row as an immutable
raw_item, and enqueue ``parse_raw_item`` — the rule-based UZEX-style parser —
for each newly inserted raw_item. html_table rows are already structured
(column-mapped product/price/volume), so they match products against the
synonym dictionary at zero LLM cost; unrecognized rows are queued for
classification exactly like UZEX rows.

Reuses the per-source isolation helper (run_source_fetch_isolated) so a failure
in one source cannot abort the batch or affect siblings (T-02-17).

Beat schedule (schedule.py): 'html_table_fetch' at crontab(minute=15) → hourly.
Queue: 'ingest'.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="html_table_fetch")  # type: ignore[untyped-decorator]
def html_table_fetch() -> dict[str, Any]:
    """Fetch all enabled html_table sources and enqueue rule-based parsing per new item.

    Returns:
        Dict with keys: status, adapter, sources_processed, total_inserted, errors.
    """
    import app.ingest.html_table  # noqa: F401, PLC0415 — triggers adapter self-registration
    from app.core.db import engine  # noqa: PLC0415
    from app.ingest.registry import get_adapter  # noqa: PLC0415
    from app.tasks.ingest import (  # noqa: PLC0415
        _load_enabled_sources,
        run_source_fetch_isolated,
    )

    logger.info("html_table_fetch.start")
    adapter = get_adapter("html_table")

    sources_processed = 0
    total_inserted = 0

    with Session(engine) as session:
        sources = _load_enabled_sources(session, "html_table")

        if not sources:
            logger.info("html_table_fetch.no_enabled_sources")
            return {
                "status": "ok",
                "adapter": "html_table",
                "sources_processed": 0,
                "total_inserted": 0,
                "errors": [],
            }

        for source in sources:
            inserted = run_source_fetch_isolated(
                session, source, adapter, parse_task_name="parse_raw_item"
            )
            total_inserted += inserted
            sources_processed += 1

    logger.info(
        "html_table_fetch.done",
        extra={"sources": sources_processed, "inserted": total_inserted},
    )
    return {
        "status": "ok",
        "adapter": "html_table",
        "sources_processed": sources_processed,
        "total_inserted": total_inserted,
        "errors": [],
    }
