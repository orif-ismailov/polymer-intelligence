"""
nightly_llm_catchup — Celery beat task: reprocess budget-deferred Telegram items.

Runs at UTC 02:00 each day (after the daily Redis budget key resets at UTC midnight).
Selects raw_items in 'budget_deferred' state from telegram_channel sources and
re-enqueues each for parse_telegram_item, in bounded batches to respect the
freshly-reset daily budget.

Design (AI-SPEC §6 G4):
  - Items marked 'budget_deferred' are items where BudgetExceeded was raised during
    parse_telegram_item. The rule-based fallback ran (so a signal was written with
    needs_review=True), but the LLM extraction was not attempted.
  - The nightly run benefits from the UTC midnight budget reset — a fresh 500K token
    budget is available from 00:00 UTC. We run at 02:00 to give the reset time to
    propagate and avoid race conditions with the last-minute budget exhaustion window.
  - Batch size is bounded (default 200) to ensure the catch-up itself stays within budget.
  - Each item's parse_status is reset to 'pending' so parse_telegram_item's
    double-parse guard does not skip it. The task handles race conditions (item already
    re-processed by a concurrent call) via the double-parse guard.

Beat entry: 'nightly_llm_catchup' at crontab(minute=0, hour=2)
Queue: 'parse' (same as parse_telegram_item)

Security:
  T-05-18: Cost-control breach is notified by raise_budget_exceeded_alert at degrade
           time. This task is the recovery path — deferred items get full LLM
           extraction when the budget resets, maintaining the audit trail (G5).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import sqlalchemy as sa

from app.tasks.celery_app import celery_app
from app.tasks.parse_telegram import enqueue_for_telegram_parse

logger = logging.getLogger(__name__)

# Maximum items to re-enqueue in a single nightly run.
# At LLM_TOKEN_ESTIMATE=1200 tokens per item, 200 items = 240,000 tokens max
# — within the default 500,000 daily budget. Items beyond the freshly-reset
# budget defer again to the next nightly run.
_CATCHUP_BATCH_LIMIT = 200


def get_session() -> Any:
    """Context manager that yields a SQLAlchemy session (test-patchable seam)."""
    from app.core.db import SessionLocal  # noqa: PLC0415

    @contextlib.contextmanager
    def _session_ctx():  # type: ignore[no-untyped-def]
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    return _session_ctx()


def check_and_reserve_tokens(estimated: int) -> None:
    """Wrapper: check token budget before starting the batch."""
    from parsing.budget import check_and_reserve_tokens as _check  # noqa: PLC0415

    _check(estimated)


@celery_app.task(name="nightly_llm_catchup")  # type: ignore[untyped-decorator]
def nightly_llm_catchup() -> dict[str, Any]:
    """Reprocess budget-deferred Telegram raw_items with LLM extraction.

    Selects up to _CATCHUP_BATCH_LIMIT raw_items in 'budget_deferred' state
    from telegram_channel sources. Resets each item's parse_status to 'pending'
    and dispatches parse_telegram_item for each.

    The task completes synchronously (it dispatches; it does not wait for results).
    Each parse_telegram_item handles its own budget check — if the budget is already
    exhausted at catch-up time, items will be deferred again until tomorrow.

    Returns:
        Dict with keys: status, deferred_items_found, enqueued.
    """
    with get_session() as session:
        # ── Find budget-deferred telegram raw_items ──────────────────────────
        rows = session.execute(
            sa.text(
                """
                SELECT ri.id
                FROM raw_items ri
                JOIN sources s ON s.id = ri.source_id
                WHERE ri.parse_status = 'budget_deferred'
                  AND s.adapter = 'telegram_channel'
                ORDER BY ri.fetched_at ASC
                LIMIT :limit
                """
            ),
            {"limit": _CATCHUP_BATCH_LIMIT},
        ).fetchall()

        if not rows:
            logger.info("nightly_catchup.no_deferred_items")
            return {"status": "ok", "deferred_items_found": 0, "enqueued": 0}

        raw_item_ids = [row[0] for row in rows]

        # ── Reset parse_status → 'pending' (clears double-parse guard) ───────
        # Use a parameterized IN clause by building a list of :param_N binds
        placeholders = ", ".join(f":id_{i}" for i in range(len(raw_item_ids)))
        params = {f"id_{i}": raw_item_ids[i] for i in range(len(raw_item_ids))}
        session.execute(
            sa.text(
                f"UPDATE raw_items SET parse_status = 'pending' WHERE id IN ({placeholders})"  # noqa: S608
            ),
            params,
        )
        session.commit()

        logger.info(
            "nightly_catchup.resetting_status",
            extra={"count": len(raw_item_ids)},
        )

    # ── Dispatch parse_telegram_item for each deferred item ──────────────────
    # Outside the session context so we're not holding a DB connection during dispatch
    enqueued = 0
    for raw_item_id in raw_item_ids:
        try:
            enqueue_for_telegram_parse(raw_item_id)
            enqueued += 1
        except Exception as exc:
            logger.error(
                "nightly_catchup.enqueue_error",
                extra={"raw_item_id": raw_item_id, "error": str(exc)},
            )

    logger.info(
        "nightly_catchup.complete",
        extra={"deferred_items_found": len(raw_item_ids), "enqueued": enqueued},
    )

    return {
        "status": "ok",
        "deferred_items_found": len(raw_item_ids),
        "enqueued": enqueued,
    }
