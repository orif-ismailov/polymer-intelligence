"""
parse_raw_item — rule-based UZEX signal extraction Celery task.

Reads a pending UZEX raw_item by ID and routes it through the parse pipeline:

  match_product(product_text) →
    (a) polymer match (product_id found)   → create Signal, set parse_status='parsed'
    (b) no match (unrecognized)            → queue_for_classification, set parse_status='irrelevant'

Every parse is journaled in parse_runs with:
    parser = 'uzex_table_v1'
    model  = NULL  (rule-based, not LLM)

Design notes:
  - One task per raw_item_id: a failure in one item does NOT affect siblings (T-02-17).
  - Unrecognized goods are NOT a source_failure (REQ-uzex-parser): consecutive_failures
    is NEVER touched in the unrecognized branch.
  - Double-parse guard: if raw_item.parse_status != 'pending', return immediately
    (no duplicate signals).
  - Grade extraction via grade_service.extract_grade (regex + DB lookup).
  - Signal construction via signal_service.create_signal_from_parse.

Security:
  T-02-15: Decimal coercion delegated to signal_service._safe_decimal.
  T-02-16: All DB access via ORM or bound parameters (no f-string SQL).
  T-02-17: try/except wraps the whole parse body; errors → parse_runs status='error'.
  T-02-18: Every parse writes a parse_runs row (full provenance journal).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

PARSER_NAME = "uzex_table_v1"


def get_session() -> Any:
    """Context manager that yields a SQLAlchemy session.

    Used as a seam for testing (can be patched).
    """
    from app.core.db import SessionLocal  # noqa: PLC0415

    @contextlib.contextmanager
    def _session_ctx():  # type: ignore[no-untyped-def]
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    return _session_ctx()


# Thin wrappers so tests can patch them cleanly
def match_product(session: Any, text_: str) -> int | None:
    """Wrapper: route through relevance_service.match_product."""
    from app.services.relevance_service import match_product as _match  # noqa: PLC0415

    return _match(session, text_)


def queue_for_classification(
    session: Any, raw_item_id: int, product_text: str
) -> None:
    """Wrapper: route through relevance_service.queue_for_classification."""
    from app.services.relevance_service import (  # noqa: PLC0415
        queue_for_classification as _queue,
    )

    _queue(session, raw_item_id, product_text)


def create_signal_from_parse(session: Any, raw_item: Any, parsed: Mapping[str, object]) -> Any:
    """Wrapper: route through signal_service.create_signal_from_parse."""
    from app.services.signal_service import (  # noqa: PLC0415
        create_signal_from_parse as _create,
    )

    return _create(session, raw_item, parsed)


@celery_app.task(name="parse_raw_item")  # type: ignore[untyped-decorator]
def parse_raw_item(raw_item_id: int) -> dict[str, Any]:
    """Parse a single UZEX raw_item into the signals stream.

    Args:
        raw_item_id: The raw_items.id to parse.

    Returns:
        Dict with keys: status, signal_id (if created), error (if any).

    Routing:
        - polymer match  → signal created, parse_status='parsed'
        - no match       → manual_classification_queue, parse_status='irrelevant'
        - already parsed → immediate return (idempotency guard)
        - error          → parse_runs status='error', parse_status='failed'
    """
    from app.models.sources import ParseRun, RawItem  # noqa: PLC0415
    from app.services.grade_service import extract_grade  # noqa: PLC0415

    with get_session() as session:
        # ── Load raw_item ──────────────────────────────────────────────────────
        raw_item = session.get(RawItem, raw_item_id)
        if raw_item is None:
            logger.warning(
                "parse_raw_item.not_found", extra={"raw_item_id": raw_item_id}
            )
            return {"status": "not_found", "raw_item_id": raw_item_id}

        # ── Double-parse guard ─────────────────────────────────────────────────
        if raw_item.parse_status != "pending":
            logger.info(
                "parse_raw_item.already_parsed",
                extra={"raw_item_id": raw_item_id, "status": raw_item.parse_status},
            )
            return {"status": "already_parsed", "raw_item_id": raw_item_id}

        payload: dict[str, Any] = raw_item.payload or {}
        product_text = str(payload.get("product_text", "")).strip()

        try:
            # ── Relevance check ────────────────────────────────────────────────
            product_id = match_product(session, product_text)

            if product_id is not None:
                # ── Branch (a): polymer match → create signal ──────────────────
                # WR-05: UZEX adapters do not populate 'grade_text' in the payload;
                # the full product description (e.g. "ПП T30S Шуртан") lives in
                # 'product_text'. Fall back to product_text so grade linking works
                # for UZEX sources (grade_text from other adapters still wins when set).
                grade_text_raw = (
                    str(payload.get("grade_text", "")).strip()
                    or str(payload.get("product_text", "")).strip()
                )
                grade_id, grade_text = extract_grade(grade_text_raw, session)

                parsed = {
                    "product_id": product_id,
                    "grade_id": grade_id,
                    "grade_text": grade_text,
                }

                signal = create_signal_from_parse(session, raw_item, parsed)
                session.add(signal)
                session.flush()  # get signal.id

                raw_item.parse_status = "parsed"

                parse_run = ParseRun(
                    raw_item_id=raw_item_id,
                    parser=PARSER_NAME,
                    model=None,  # rule-based: model IS NULL (T-02-18)
                    prompt_version=None,
                    result={"signal_id": signal.id, "product_id": product_id},
                    status="ok",
                    error=None,
                )
                session.add(parse_run)
                session.commit()

                logger.info(
                    "parse_raw_item.parsed",
                    extra={
                        "raw_item_id": raw_item_id,
                        "signal_id": signal.id,
                        "product_id": product_id,
                    },
                )
                return {"status": "parsed", "signal_id": signal.id, "raw_item_id": raw_item_id}

            else:
                # ── Branch (b): no polymer match → irrelevant (+ queue for review) ──
                # Per dev-spec §2.1 + ROADMAP SC#4: a non-matched row is marked
                # parse_status='irrelevant' (kept out of signals; the weekly
                # irrelevant-goods report keys on this status). It is ALSO queued for
                # manual classification so the synonyms dictionary can be topped up.
                # NOTE: This is NOT a source_failure (REQ-uzex-parser).
                # Do NOT modify sources.consecutive_failures here — unrecognized goods
                # are expected (new products, typos) and must not trigger source alerts.
                queue_for_classification(session, raw_item_id, product_text)
                raw_item.parse_status = "irrelevant"

                parse_run = ParseRun(
                    raw_item_id=raw_item_id,
                    parser=PARSER_NAME,
                    model=None,  # rule-based: model IS NULL (T-02-18)
                    prompt_version=None,
                    result={"note": "unrecognized_product", "product_text": product_text[:512]},
                    status="ok",
                    error=None,
                )
                session.add(parse_run)
                session.commit()

                logger.info(
                    "parse_raw_item.unrecognized",
                    extra={
                        "raw_item_id": raw_item_id,
                        "product_text": product_text[:100],
                    },
                )
                return {
                    "status": "irrelevant",
                    "raw_item_id": raw_item_id,
                    "reason": "unrecognized_product",
                }

        except Exception as exc:
            # ── Error path: journal to parse_runs, set parse_status='failed' ──
            # (T-02-17: per-item failure does NOT crash sibling tasks)
            try:
                raw_item.parse_status = "failed"
                parse_run = ParseRun(
                    raw_item_id=raw_item_id,
                    parser=PARSER_NAME,
                    model=None,
                    prompt_version=None,
                    result=None,
                    status="error",
                    error=str(exc)[:1000],
                )
                session.add(parse_run)
                session.commit()
            except Exception as inner_exc:
                logger.error(
                    "parse_raw_item.journal_error",
                    extra={"raw_item_id": raw_item_id, "error": str(inner_exc)},
                )

            logger.error(
                "parse_raw_item.error",
                extra={"raw_item_id": raw_item_id, "error": str(exc)},
            )
            return {"status": "error", "raw_item_id": raw_item_id, "error": str(exc)}
