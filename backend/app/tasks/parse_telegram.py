"""
parse_telegram_item — Celery task: Telegram LLM extraction orchestrator.

Implements the full AI extraction pipeline for a single telegram raw_item,
enforcing the AI-SPEC §6 guardrails G1-G6:

  G1  Exactly ONE LLM call per item (budget gate + instructor max_retries=2)
  G2  confidence < CONFIDENCE_REVIEW_THRESHOLD → signal written with needs_review=True,
      never auto-published as HOT regardless of lead_score
  G3  InstructorRetryException dead-letter: parse_runs.status='error', no signal
  G4  BudgetExceeded → rule_based_extract + nightly_reprocess enqueued + budget alert
  G5  parse_runs row is ALWAYS written before the signal (attribution invariant)
  G6  Blank/media-only content → marked irrelevant WITHOUT calling extract_signal
      (cost guard — no token spend for empty messages)

Flow (§4 Core Pattern):
  1. Load raw_item; double-parse guard (return if parse_status != 'pending')
  2. prepare_message_text(raw_item.content) → blank check (G6)
  3. check_and_reserve_tokens(LLM_TOKEN_ESTIMATE) — raises BudgetExceeded
  4. extract_signal(prepared_text) → (ExtractionResult, journal)
     record_actual_tokens to reconcile conservative pre-estimate
     OR: BudgetExceeded → rule_based_extract, deferred journal, nightly enqueue, alert
     OR: InstructorRetryException → write error parse_run, set failed, return
  5. write_parse_run FIRST (G5 attribution ordering)
  6. if result.is_relevant: create_signal_from_extraction + add + flush; parse_status='parsed'
     else: parse_status='irrelevant'
  7. commit

Security:
  T-05-15: G5 — write_parse_run before signal always; asserted by test_attribution_invariant
  T-05-16: G3 — InstructorRetryException path never writes a partial signal
  T-05-17: G2 — confidence<0.5 always sets needs_review=True (never auto-HOT)
  T-05-18: G4 — BudgetExceeded degrades gracefully; never indefinite block
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from instructor.core import InstructorRetryException

from app.tasks.celery_app import celery_app
from parsing.budget import (
    BudgetExceeded,
    check_and_reserve_tokens,
    record_actual_tokens,
    release_reservation,
)
from parsing.fallback import rule_based_extract
from parsing.schemas import CONFIDENCE_REVIEW_THRESHOLD
from parsing.text_prep import prepare_message_text

logger = logging.getLogger(__name__)

# Conservative per-call token ceiling for the budget pre-reservation (WR-02).
# Set close to the realistic upper bound of (tokens_in + tokens_out) for one
# extraction call: non-cached input (message text + tool/schema preamble) plus
# up to max_tokens=512 of output. The previous 400 estimate massively
# under-reserved, letting true spend overshoot DAILY_TOKEN_LIMIT before
# record_actual_tokens reconciled. cache_read tokens are intentionally EXCLUDED
# from the budget (cached prompt prefix is billed at a fraction of input cost and
# is not counted toward the daily token cap). Actual spend is reconciled by
# record_actual_tokens after a successful LLM call.
LLM_TOKEN_ESTIMATE = 1200


# --------------------------------------------------------------------------
# Session seam (patchable in tests — mirrors parse.py pattern)
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Thin wrappers (patchable in tests — mirrors parse.py pattern)
# --------------------------------------------------------------------------


def extract_signal(prepared_text: str) -> tuple[Any, dict]:
    """Wrapper: call parsing.extractor.extract_signal."""
    from parsing.extractor import extract_signal as _extract  # noqa: PLC0415

    return _extract(prepared_text)


def write_parse_run(session: Any, raw_item_id: int, **kwargs: Any) -> int:
    """Wrapper: call ai_signal_service.write_parse_run."""
    from app.domains.signals.ai import write_parse_run as _write  # noqa: PLC0415

    return _write(session, raw_item_id, **kwargs)


def create_signal_from_extraction(session: Any, raw_item: Any, result: Any, journal: dict, **kwargs: Any) -> Any:
    """Wrapper: call ai_signal_service.create_signal_from_extraction."""
    from app.domains.signals.ai import (  # noqa: PLC0415
        create_signal_from_extraction as _create,
    )

    return _create(session, raw_item, result, journal, **kwargs)


def raise_budget_exceeded_alert(session: Any) -> None:
    """Wrapper: call ai_signal_service.raise_budget_exceeded_alert."""
    from app.domains.signals.ai import (  # noqa: PLC0415
        raise_budget_exceeded_alert as _raise,
    )

    _raise(session)


def delete_existing_signals(session: Any, raw_item_id: int) -> int:
    """Delete any Signal rows already written for a raw_item (idempotency guard).

    A raw_item that was budget-deferred has a rule-based Signal written during the
    degrade pass. When nightly_llm_catchup re-parses it with the LLM, this guard
    supersedes the stale rule-based Signal so we never end up with two feed entries
    (one rule-based, one LLM) for one source message (CR-03). On the normal first
    pass this deletes nothing.

    Returns the number of rows deleted.
    """
    from app.domains.signals.models import Signal  # noqa: PLC0415

    deleted = (
        session.query(Signal)
        .filter(Signal.raw_item_id == raw_item_id)
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info(
            "parse_telegram.superseded_existing_signals",
            extra={"raw_item_id": raw_item_id, "deleted": deleted},
        )
    return deleted


def match_product(session: Any, text_: str) -> int | None:
    """Wrapper: call relevance_service.match_product."""
    from app.domains.reference.relevance import match_product as _match  # noqa: PLC0415

    return _match(session, text_)


def extract_grade(text_: str, session: Any) -> tuple[int | None, str | None]:
    """Wrapper: call grade_service.extract_grade."""
    from app.domains.reference.grades import extract_grade as _extract  # noqa: PLC0415

    return _extract(text_, session)


def enqueue_nightly_reprocess(raw_item_id: int) -> None:
    """Mark item for nightly catch-up; called on BudgetExceeded path.

    The raw_item.parse_status stays 'pending' so the nightly_llm_catchup
    task can find and re-enqueue it. This function is also called by the
    catchup task itself to set parse_status back to 'pending' after clearing
    a 'budget_deferred' state if we use that marker. For now: the item's
    parse_status is set to 'budget_deferred' to distinguish from plain pending.
    """
    # In the current design we set parse_status='budget_deferred' (a re-processable
    # state) on the raw_item. The nightly catch-up task queries for this status.
    # This function is intentionally a no-op here — the status is set by the caller
    # in parse_telegram_item; the nightly task picks it up. Provided as a hook for
    # future explicit nightly queue mechanics (e.g. a Redis reprocess set).
    logger.info(
        "parse_telegram.enqueue_nightly_reprocess",
        extra={"raw_item_id": raw_item_id},
    )


# --------------------------------------------------------------------------
# Celery task
# --------------------------------------------------------------------------


@celery_app.task(name="parse_telegram_item")  # type: ignore[untyped-decorator]
def parse_telegram_item(raw_item_id: int) -> dict[str, Any]:
    """Parse a single Telegram raw_item through the AI extraction pipeline.

    Enforces AI-SPEC §6 guardrails G1-G6 as described in module docstring.

    Args:
        raw_item_id: The raw_items.id to parse.

    Returns:
        Dict with keys: status, signal_id (if created), error (if any).

    Routing:
        - happy path (relevant, confidence >= 0.5) → signal created, needs_review=False
        - low confidence (< 0.5)               → signal created, needs_review=True (G2)
        - irrelevant                            → parse_status='irrelevant', no signal
        - blank/media-only                      → parse_status='irrelevant', no LLM call (G6)
        - InstructorRetryException              → parse_status='failed', no signal (G3)
        - BudgetExceeded                        → rule_based fallback + deferred + alert (G4)
        - already parsed (double-parse guard)   → immediate return (idempotency)
    """
    from app.domains.signals.source_models import RawItem  # noqa: PLC0415

    with get_session() as session:
        # ── Load raw_item ──────────────────────────────────────────────────────
        raw_item = session.get(RawItem, raw_item_id)
        if raw_item is None:
            logger.warning(
                "parse_telegram.not_found",
                extra={"raw_item_id": raw_item_id},
            )
            return {"status": "not_found", "raw_item_id": raw_item_id}

        # ── Double-parse guard (G0 idempotency) ───────────────────────────────
        if raw_item.parse_status != "pending":
            logger.info(
                "parse_telegram.already_parsed",
                extra={"raw_item_id": raw_item_id, "status": raw_item.parse_status},
            )
            return {"status": "already_parsed", "raw_item_id": raw_item_id}

        # ── G6: Blank/media-only content guard ────────────────────────────────
        prepared = prepare_message_text(raw_item.content or "")
        if prepared == "":
            # No text to extract from — journal as irrelevant (no LLM call)
            write_parse_run(
                session,
                raw_item_id,
                parser="llm_extract_tools",
                model=None,
                prompt_version=None,
                tokens_in=0,
                tokens_out=0,
                latency_ms=0,
                result={"note": "blank_or_media_only"},
                status="ok",
                error=None,
            )
            raw_item.parse_status = "irrelevant"
            session.commit()
            logger.info(
                "parse_telegram.blank_content",
                extra={"raw_item_id": raw_item_id},
            )
            return {"status": "irrelevant", "raw_item_id": raw_item_id, "reason": "blank_content"}

        # ── G3: InstructorRetryException dead-letter path ─────────────────────
        # Attempt the budget gate + LLM call. InstructorRetryException propagates
        # immediately (G3) — no signal is created.
        try:
            # ── G4: Budget gate ──────────────────────────────────────────────
            try:
                check_and_reserve_tokens(LLM_TOKEN_ESTIMATE)
                result, journal = extract_signal(prepared)
                # Reconcile actual token spend
                actual_tokens = journal.get("tokens_in", 0) + journal.get("tokens_out", 0)
                record_actual_tokens(LLM_TOKEN_ESTIMATE, actual_tokens)

            except BudgetExceeded:
                # ── G4: Budget degrade → rule_based_extract ──────────────────
                logger.warning(
                    "parse_telegram.budget_exceeded_fallback",
                    extra={"raw_item_id": raw_item_id},
                )
                result = rule_based_extract(prepared)
                journal = {
                    "parser": "rule_based_fallback",
                    "model": None,
                    "prompt_version": None,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cache_read_tokens": 0,
                    "latency_ms": 0,
                    "raw_response": {},
                }
                # Mark for nightly catch-up (status='budget_deferred' re-processable)
                raw_item.parse_status = "budget_deferred"  # type: ignore[assignment]
                enqueue_nightly_reprocess(raw_item_id)
                raise_budget_exceeded_alert(session)

        except InstructorRetryException as exc:
            # ── G3: Dead-letter — all retries failed ──────────────────────────
            # Reservation was made but the call produced no usage — refund it so a
            # failing API can't drain the daily budget (Phase 8g).
            release_reservation(LLM_TOKEN_ESTIMATE)
            logger.error(
                "parse_telegram.dead_letter",
                extra={"raw_item_id": raw_item_id, "error": str(exc)},
            )
            write_parse_run(
                session,
                raw_item_id,
                parser="llm_extract_tools",
                model=None,
                prompt_version=None,
                tokens_in=0,
                tokens_out=0,
                latency_ms=0,
                result={"raw": "failed_attempts"},
                status="error",
                error=str(exc)[:1000],
            )
            raw_item.parse_status = "failed"
            session.commit()
            return {
                "status": "dead_lettered",
                "raw_item_id": raw_item_id,
                "error": str(exc)[:200],
            }

        # ── G5: Attribution invariant — parse_runs FIRST, then signal ────────
        parse_run_id = write_parse_run(
            session,
            raw_item_id,
            parser=journal.get("parser", "llm_extract_tools"),
            model=journal.get("model"),
            prompt_version=journal.get("prompt_version"),
            tokens_in=journal.get("tokens_in", 0),
            tokens_out=journal.get("tokens_out", 0),
            latency_ms=journal.get("latency_ms", 0),
            # mode="json": Decimal volume/price + enum kind must serialise into the
            # JSONB result column (plain model_dump() leaves Decimal → json.dumps fails).
            result={"extraction": result.model_dump(mode="json") if hasattr(result, "model_dump") else {}},
            status="ok",
            error=None,
        )

        # ── Signal write (if relevant) ────────────────────────────────────────
        if result.is_relevant:
            # G2: confidence < 0.5 → needs_review=True (never auto-published HOT)
            needs_review = result.confidence < CONFIDENCE_REVIEW_THRESHOLD

            # CR-03 idempotency: supersede any Signal already written for this
            # raw_item (e.g. the rule-based Signal from a prior budget-deferred
            # pass) so a catch-up reprocess updates rather than duplicates.
            delete_existing_signals(session, raw_item_id)

            signal = create_signal_from_extraction(
                session,
                raw_item,
                result,
                journal,
                needs_review=needs_review,
            )
            session.add(signal)
            session.flush()

            # Only set parse_status='parsed' if we didn't set 'budget_deferred'
            if raw_item.parse_status != "budget_deferred":
                raw_item.parse_status = "parsed"

            session.commit()

            logger.info(
                "parse_telegram.signal_created",
                extra={
                    "raw_item_id": raw_item_id,
                    "signal_id": signal.id,
                    "needs_review": needs_review,
                    "parse_run_id": parse_run_id,
                },
            )
            return {
                "status": "parsed",
                "signal_id": signal.id,
                "raw_item_id": raw_item_id,
                "needs_review": needs_review,
            }

        else:
            # Irrelevant: no signal written
            if raw_item.parse_status != "budget_deferred":
                raw_item.parse_status = "irrelevant"
            session.commit()

            logger.info(
                "parse_telegram.irrelevant",
                extra={"raw_item_id": raw_item_id, "parse_run_id": parse_run_id},
            )
            return {"status": "irrelevant", "raw_item_id": raw_item_id}


# --------------------------------------------------------------------------
# Helper: enqueue a raw_item for telegram parsing
# --------------------------------------------------------------------------


def enqueue_for_telegram_parse(raw_item_id: int) -> None:
    """Dispatch parse_telegram_item.delay(raw_item_id) to the parse queue.

    Called by the userbot message handler after save_raw_items to kick off
    the AI extraction pipeline asynchronously.

    Args:
        raw_item_id: The raw_items.id to enqueue for parsing.
    """
    parse_telegram_item.delay(raw_item_id)
    logger.debug(
        "parse_telegram.enqueued",
        extra={"raw_item_id": raw_item_id},
    )
