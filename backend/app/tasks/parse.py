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


# ── LLM-fallback seam (feature-flagged; mirrors parse_telegram_item) ───────────
# These thin wrappers exist so tests can patch app.tasks.parse.<name>. They are
# only exercised when settings.UZEX_LLM_FALLBACK_ENABLED is True.

# Conservative per-call token reservation (matches parse_telegram LLM_TOKEN_ESTIMATE).
LLM_TOKEN_ESTIMATE = 1200


def _llm_fallback_enabled() -> bool:
    """Return the UZEX_LLM_FALLBACK_ENABLED flag (patchable seam for tests)."""
    from app.core.config import settings  # noqa: PLC0415

    return bool(settings.UZEX_LLM_FALLBACK_ENABLED)


def llm_extract_signal(prepared_text: str) -> tuple[Any, dict]:
    """Wrapper: call parsing.extractor.extract_signal."""
    from parsing.extractor import extract_signal as _extract  # noqa: PLC0415

    return _extract(prepared_text)


# Per-call token reservation for the news extractor (patchable seam for tests).
NEWS_TOKEN_ESTIMATE = 1200


def news_extract_signal(
    prepared_text: str, *, model: str | None = None, prompt_version: str | None = None
) -> tuple[Any, dict]:
    """Wrapper: call parsing.news_extractor.extract_news with optional runtime overrides."""
    from parsing.news_extractor import DEFAULT_MODEL, NEWS_PROMPT_VERSION  # noqa: PLC0415
    from parsing.news_extractor import extract_news as _extract  # noqa: PLC0415

    return _extract(
        prepared_text,
        model=model or DEFAULT_MODEL,
        prompt_version=prompt_version or NEWS_PROMPT_VERSION,
    )


def check_and_reserve_tokens(estimated: int) -> None:
    """Wrapper: call parsing.budget.check_and_reserve_tokens."""
    from parsing.budget import check_and_reserve_tokens as _check  # noqa: PLC0415

    _check(estimated)


def record_actual_tokens(reserved: int, actual: int) -> None:
    """Wrapper: call parsing.budget.record_actual_tokens."""
    from parsing.budget import record_actual_tokens as _record  # noqa: PLC0415

    _record(reserved, actual)


def release_reserved_tokens(reserved: int) -> None:
    """Wrapper: refund a reservation whose LLM call failed (no usage produced)."""
    from parsing.budget import release_reservation as _release  # noqa: PLC0415

    _release(reserved)


def write_parse_run(session: Any, raw_item_id: int, **kwargs: Any) -> int:
    """Wrapper: call ai_signal_service.write_parse_run."""
    from app.services.ai_signal_service import write_parse_run as _write  # noqa: PLC0415

    return _write(session, raw_item_id, **kwargs)


def create_signal_from_extraction(
    session: Any, raw_item: Any, result: Any, journal: dict, **kwargs: Any
) -> Any:
    """Wrapper: call ai_signal_service.create_signal_from_extraction."""
    from app.services.ai_signal_service import (  # noqa: PLC0415
        create_signal_from_extraction as _create,
    )

    return _create(session, raw_item, result, journal, **kwargs)


def _parse_via_llm(session: Any, raw_item: Any, product_text: str) -> dict[str, Any]:
    """Route an unrecognized UZEX row through the LLM extractor (like Telegram).

    Mirrors the parse_telegram_item guardrails:
      - G6 blank-content guard (no LLM call for empty content)
      - G4 budget gate; on BudgetExceeded it DEGRADES to the rule-based path
        (queue_for_classification + irrelevant) rather than 'budget_deferred', because
        nightly_llm_catchup only reprocesses telegram_channel items — using
        budget_deferred here would strand the row. Re-enable later / raise the budget
        to LLM-process it.
      - G3 InstructorRetryException dead-letter (parse_status='failed', no signal)
      - G5 parse_runs row written before the signal
      - G2 confidence < threshold → needs_review=True

    product_id resolution happens inside create_signal_from_extraction via
    match_product on the LLM's canonical product code (e.g. "PVC").
    """
    from instructor.core import InstructorRetryException  # noqa: PLC0415

    from parsing.budget import BudgetExceeded  # noqa: PLC0415
    from parsing.schemas import CONFIDENCE_REVIEW_THRESHOLD  # noqa: PLC0415
    from parsing.text_prep import prepare_message_text  # noqa: PLC0415

    prepared = prepare_message_text(raw_item.content or "")
    if not prepared:
        write_parse_run(
            session, raw_item.id, parser="llm_extract_tools", model=None,
            prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
            result={"note": "blank_content"}, status="ok", error=None,
        )
        raw_item.parse_status = "irrelevant"
        session.commit()
        return {"status": "irrelevant", "raw_item_id": raw_item.id, "reason": "blank_content"}

    try:
        check_and_reserve_tokens(LLM_TOKEN_ESTIMATE)
        result, journal = llm_extract_signal(prepared)
        record_actual_tokens(
            LLM_TOKEN_ESTIMATE,
            int(journal.get("tokens_in", 0)) + int(journal.get("tokens_out", 0)),
        )
    except BudgetExceeded:
        # G4 degrade → today's rule-based no-match behaviour (queue + irrelevant).
        logger.warning("parse_raw_item.budget_exceeded_degrade", extra={"raw_item_id": raw_item.id})
        queue_for_classification(session, raw_item.id, product_text)
        write_parse_run(
            session, raw_item.id, parser="rule_based_fallback", model=None,
            prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
            result={"note": "budget_exceeded_degraded"}, status="ok", error=None,
        )
        raw_item.parse_status = "irrelevant"
        session.commit()
        return {"status": "irrelevant", "raw_item_id": raw_item.id, "reason": "budget_exceeded"}
    except InstructorRetryException as exc:
        # The reservation was made but the call produced no usage — refund it so a
        # failing API can't drain the daily budget (Phase 8g).
        release_reserved_tokens(LLM_TOKEN_ESTIMATE)
        logger.error("parse_raw_item.dead_letter", extra={"raw_item_id": raw_item.id, "error": str(exc)})
        write_parse_run(
            session, raw_item.id, parser="llm_extract_tools", model=None,
            prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
            result={"raw": "failed_attempts"}, status="error", error=str(exc)[:1000],
        )
        raw_item.parse_status = "failed"
        session.commit()
        return {"status": "dead_lettered", "raw_item_id": raw_item.id, "error": str(exc)[:200]}

    # G5: attribution — parse_runs first, then signal.
    write_parse_run(
        session, raw_item.id, parser=journal.get("parser", "llm_extract_tools"),
        model=journal.get("model"), prompt_version=journal.get("prompt_version"),
        tokens_in=int(journal.get("tokens_in", 0)), tokens_out=int(journal.get("tokens_out", 0)),
        latency_ms=journal.get("latency_ms", 0),
        # mode="json" so Decimal volume/price + enum kind serialise into the JSONB
        # audit column (plain model_dump() leaves Decimal, which json.dumps rejects).
        result={"extraction": result.model_dump(mode="json") if hasattr(result, "model_dump") else {}},
        status="ok", error=None,
    )

    if result.is_relevant:
        needs_review = result.confidence < CONFIDENCE_REVIEW_THRESHOLD
        signal = create_signal_from_extraction(
            session, raw_item, result, journal, needs_review=needs_review
        )
        session.add(signal)
        session.flush()
        raw_item.parse_status = "parsed"
        session.commit()
        logger.info(
            "parse_raw_item.llm_signal",
            extra={"raw_item_id": raw_item.id, "signal_id": signal.id, "needs_review": needs_review},
        )
        return {
            "status": "parsed", "signal_id": signal.id,
            "raw_item_id": raw_item.id, "needs_review": needs_review, "via": "llm",
        }

    raw_item.parse_status = "irrelevant"
    session.commit()
    logger.info("parse_raw_item.llm_irrelevant", extra={"raw_item_id": raw_item.id})
    return {"status": "irrelevant", "raw_item_id": raw_item.id, "via": "llm"}


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

            elif _llm_fallback_enabled():
                # ── Branch (b'): no rule-based match → LLM extraction (like Telegram) ──
                # When UZEX_LLM_FALLBACK_ENABLED, route the unrecognized row through the
                # LLM extractor instead of straight to the manual-classification queue.
                # _parse_via_llm owns its own commit + parse_runs journaling.
                return _parse_via_llm(session, raw_item, product_text)

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


@celery_app.task(name="parse_xarid_item")  # type: ignore[untyped-decorator]
def parse_xarid_item(raw_item_id: int) -> dict[str, Any]:
    """Parse a xarid procurement raw_item into a buy_request signal.

    xarid rows are STRUCTURED buy-side tenders (kind_hint='buy_request') that already
    carry the buyer, quantity, price, location, and contact. Only the PRODUCT needs
    resolving, and — unlike parse_raw_item (UZEX exchange rows) — a miss must NOT drop
    the row on the exact-match dictionary alone, because procurement descriptions
    ("Тройник полипропиленовый") rarely match it verbatim. Resolution order:

      1. exact synonym dictionary (cheap) — clean polymer names,
      2. on a miss, the budget-gated LLM extractor, whose canonical product code
         (e.g. 'PP') resolves via the same dictionary AND doubles as the relevance
         filter: rows it cannot map to a polymer are marked irrelevant (dropped),
         keeping procurement noise (salt, disinfectant, instruments) out.

    Kind is FORCED to buy_request; the buyer's phone/email/tender_url stay in the
    payload and are surfaced by the live-feed contact join. Mirrors parse_raw_item's
    guards (double-parse, budget degrade, dead-letter, per-item error isolation).
    """
    from instructor.core import InstructorRetryException  # noqa: PLC0415

    from app.models.sources import RawItem  # noqa: PLC0415
    from app.services.grade_service import extract_grade  # noqa: PLC0415
    from app.services.signal_service import (  # noqa: PLC0415
        create_buy_request_signal_from_xarid,
    )
    from parsing.budget import BudgetExceeded  # noqa: PLC0415
    from parsing.text_prep import prepare_message_text  # noqa: PLC0415

    with get_session() as session:
        raw_item = session.get(RawItem, raw_item_id)
        if raw_item is None:
            logger.warning("parse_xarid_item.not_found", extra={"raw_item_id": raw_item_id})
            return {"status": "not_found", "raw_item_id": raw_item_id}
        if raw_item.parse_status != "pending":
            logger.info(
                "parse_xarid_item.already_parsed",
                extra={"raw_item_id": raw_item_id, "status": raw_item.parse_status},
            )
            return {"status": "already_parsed", "raw_item_id": raw_item_id}

        payload: dict[str, Any] = raw_item.payload or {}
        product_text = str(payload.get("product_text", "")).strip()
        journal: dict[str, Any] = {}
        via = "rule_based"

        try:
            # 1. exact synonym dictionary
            product_id = match_product(session, product_text)

            # 2. LLM product resolution on a dictionary miss (budget-gated)
            if product_id is None:
                prepared = prepare_message_text(raw_item.content or "")
                if prepared:
                    try:
                        check_and_reserve_tokens(LLM_TOKEN_ESTIMATE)
                        result, journal = llm_extract_signal(prepared)
                        record_actual_tokens(
                            LLM_TOKEN_ESTIMATE,
                            int(journal.get("tokens_in", 0)) + int(journal.get("tokens_out", 0)),
                        )
                        via = "llm"
                        product_id = match_product(
                            session, (result.product or result.grade_text or "")
                        )
                    except BudgetExceeded:
                        logger.warning(
                            "parse_xarid_item.budget_exceeded_degrade",
                            extra={"raw_item_id": raw_item_id},
                        )
                        queue_for_classification(session, raw_item_id, product_text)
                        write_parse_run(
                            session, raw_item_id, parser="rule_based_fallback", model=None,
                            prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
                            result={"note": "budget_exceeded_degraded"}, status="ok", error=None,
                        )
                        raw_item.parse_status = "irrelevant"
                        session.commit()
                        return {
                            "status": "irrelevant", "raw_item_id": raw_item_id,
                            "reason": "budget_exceeded",
                        }
                    except InstructorRetryException as exc:
                        release_reserved_tokens(LLM_TOKEN_ESTIMATE)  # refund leaked reservation
                        logger.error(
                            "parse_xarid_item.dead_letter",
                            extra={"raw_item_id": raw_item_id, "error": str(exc)},
                        )
                        write_parse_run(
                            session, raw_item_id, parser="llm_extract_tools", model=None,
                            prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
                            result={"raw": "failed_attempts"}, status="error", error=str(exc)[:1000],
                        )
                        raw_item.parse_status = "failed"
                        session.commit()
                        return {
                            "status": "dead_lettered", "raw_item_id": raw_item_id,
                            "error": str(exc)[:200],
                        }

            _parser = journal.get("parser", "llm_extract_tools") if via == "llm" else PARSER_NAME

            # 3. product still unresolved → not polymer demand → drop (noise filter)
            if product_id is None:
                queue_for_classification(session, raw_item_id, product_text)
                write_parse_run(
                    session, raw_item_id, parser=_parser, model=journal.get("model"),
                    prompt_version=journal.get("prompt_version"),
                    tokens_in=int(journal.get("tokens_in", 0)),
                    tokens_out=int(journal.get("tokens_out", 0)),
                    latency_ms=journal.get("latency_ms", 0),
                    result={"note": "no_product_match", "product_text": product_text[:512]},
                    status="ok", error=None,
                )
                raw_item.parse_status = "irrelevant"
                session.commit()
                logger.info(
                    "parse_xarid_item.unrecognized",
                    extra={"raw_item_id": raw_item_id, "via": via},
                )
                return {"status": "irrelevant", "raw_item_id": raw_item_id, "via": via}

            # 4. build the buy_request signal from the structured payload
            grade_id, grade_text = extract_grade(product_text, session)
            signal = create_buy_request_signal_from_xarid(
                session, raw_item, product_id=product_id, grade_id=grade_id, grade_text=grade_text,
            )
            session.add(signal)
            session.flush()  # get signal.id
            raw_item.parse_status = "parsed"
            write_parse_run(
                session, raw_item_id, parser=_parser, model=journal.get("model"),
                prompt_version=journal.get("prompt_version"),
                tokens_in=int(journal.get("tokens_in", 0)),
                tokens_out=int(journal.get("tokens_out", 0)),
                latency_ms=journal.get("latency_ms", 0),
                result={"signal_id": signal.id, "product_id": product_id, "kind": "buy_request", "via": via},
                status="ok", error=None,
            )
            session.commit()
            logger.info(
                "parse_xarid_item.parsed",
                extra={"raw_item_id": raw_item_id, "signal_id": signal.id, "via": via},
            )
            return {
                "status": "parsed", "signal_id": signal.id,
                "raw_item_id": raw_item_id, "via": via,
            }

        except Exception as exc:
            try:
                raw_item.parse_status = "failed"
                write_parse_run(
                    session, raw_item_id, parser=PARSER_NAME, model=None, prompt_version=None,
                    tokens_in=0, tokens_out=0, latency_ms=0, result=None, status="error",
                    error=str(exc)[:1000],
                )
                session.commit()
            except Exception as inner_exc:
                logger.error(
                    "parse_xarid_item.journal_error",
                    extra={"raw_item_id": raw_item_id, "error": str(inner_exc)},
                )
            logger.error(
                "parse_xarid_item.error",
                extra={"raw_item_id": raw_item_id, "error": str(exc)},
            )
            return {"status": "error", "raw_item_id": raw_item_id, "error": str(exc)}


@celery_app.task(name="parse_news_item")  # type: ignore[untyped-decorator]
def parse_news_item(raw_item_id: int) -> dict[str, Any]:
    """Classify a news raw_item into a kind='news' signal (Phase 7 News Intelligence).

    Routed here (instead of parse_telegram_item) when a source's config sets
    content_kind='news'. Runs the budget-gated news extractor and, if relevant, stores
    the rich classification (headline/category/importance/market_impact/summary…) under
    signals.ai. Mirrors the Telegram LLM guards: blank-content skip, budget degrade,
    dead-letter, per-item error isolation.
    """
    from instructor.core import InstructorRetryException  # noqa: PLC0415

    from app.models.sources import RawItem  # noqa: PLC0415
    from app.services.news_service import create_news_signal_from_article  # noqa: PLC0415
    from parsing.budget import BudgetExceeded  # noqa: PLC0415
    from parsing.news_schemas import NEWS_CONFIDENCE_REVIEW_THRESHOLD  # noqa: PLC0415
    from parsing.text_prep import prepare_message_text  # noqa: PLC0415

    with get_session() as session:
        raw_item = session.get(RawItem, raw_item_id)
        if raw_item is None:
            logger.warning("parse_news_item.not_found", extra={"raw_item_id": raw_item_id})
            return {"status": "not_found", "raw_item_id": raw_item_id}
        if raw_item.parse_status != "pending":
            return {"status": "already_parsed", "raw_item_id": raw_item_id}

        prepared = prepare_message_text(raw_item.content or "")
        if not prepared:
            write_parse_run(
                session, raw_item_id, parser="news_extract_tools", model=None,
                prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
                result={"note": "blank_content"}, status="ok", error=None,
            )
            raw_item.parse_status = "irrelevant"
            session.commit()
            return {"status": "irrelevant", "raw_item_id": raw_item_id, "reason": "blank_content"}

        # Runtime overrides (Phase 8d): model + prompt version + approval requirement.
        from app.services import settings_service  # noqa: PLC0415

        news_model = settings_service.get(session, "llm_extract_model")
        news_prompt = settings_service.get(session, "news_prompt_version")
        require_approval = settings_service.get(session, "news_require_approval")

        try:
            check_and_reserve_tokens(NEWS_TOKEN_ESTIMATE)
            article, journal = news_extract_signal(
                prepared, model=news_model, prompt_version=news_prompt
            )
            record_actual_tokens(
                NEWS_TOKEN_ESTIMATE,
                int(journal.get("tokens_in", 0)) + int(journal.get("tokens_out", 0)),
            )
        except BudgetExceeded:
            # Degrade: mark irrelevant (reprocessable later when budget frees up).
            logger.warning("parse_news_item.budget_exceeded", extra={"raw_item_id": raw_item_id})
            write_parse_run(
                session, raw_item_id, parser="news_extract_tools", model=None,
                prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
                result={"note": "budget_exceeded"}, status="ok", error=None,
            )
            raw_item.parse_status = "irrelevant"
            session.commit()
            return {"status": "irrelevant", "raw_item_id": raw_item_id, "reason": "budget_exceeded"}
        except InstructorRetryException as exc:
            release_reserved_tokens(NEWS_TOKEN_ESTIMATE)  # refund leaked reservation (Phase 8g)
            logger.error("parse_news_item.dead_letter", extra={"raw_item_id": raw_item_id, "error": str(exc)})
            write_parse_run(
                session, raw_item_id, parser="news_extract_tools", model=None,
                prompt_version=None, tokens_in=0, tokens_out=0, latency_ms=0,
                result={"raw": "failed_attempts"}, status="error", error=str(exc)[:1000],
            )
            raw_item.parse_status = "failed"
            session.commit()
            return {"status": "dead_lettered", "raw_item_id": raw_item_id, "error": str(exc)[:200]}

        # Attribution row first (G5), then the signal.
        write_parse_run(
            session, raw_item_id, parser=journal.get("parser", "news_extract_tools"),
            model=journal.get("model"), prompt_version=journal.get("prompt_version"),
            tokens_in=int(journal.get("tokens_in", 0)), tokens_out=int(journal.get("tokens_out", 0)),
            latency_ms=journal.get("latency_ms", 0),
            result={"news": article.model_dump(mode="json") if hasattr(article, "model_dump") else {}},
            status="ok", error=None,
        )

        if article.is_relevant:
            needs_review = article.confidence < NEWS_CONFIDENCE_REVIEW_THRESHOLD
            signal = create_news_signal_from_article(
                session, raw_item, article, journal,
                needs_review=needs_review, approved=not require_approval,
            )
            session.add(signal)
            session.flush()
            raw_item.parse_status = "parsed"
            session.commit()
            logger.info(
                "parse_news_item.parsed",
                extra={"raw_item_id": raw_item_id, "signal_id": signal.id, "needs_review": needs_review},
            )
            return {
                "status": "parsed", "signal_id": signal.id,
                "raw_item_id": raw_item_id, "needs_review": needs_review,
            }

        raw_item.parse_status = "irrelevant"
        session.commit()
        return {"status": "irrelevant", "raw_item_id": raw_item_id}
