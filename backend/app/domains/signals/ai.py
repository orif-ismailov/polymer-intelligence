"""
AI Signal Service — helpers for the parse_telegram_item orchestrator.

Provides three functions consumed by the 05-04 Celery task:

  write_parse_run(session, raw_item_id, *, parser, model, prompt_version,
                  tokens_in, tokens_out, latency_ms, result, status, error)
      Inserts a ParseRun row and calls session.flush() — never commits.
      Returns the ParseRun id (available after flush).

  create_signal_from_extraction(session, raw_item, result, journal, *, needs_review)
      Maps an ExtractionResult → Signal ORM object with the ai JSONB stamped:
        {lead_score, classification, needs_review, model, prompt_version,
         scored_at, scoring_prompt_version}
      Performs product_id resolution via relevance_service.match_product and
      grade_id resolution via grade_service.extract_grade.
      Returns the Signal — caller adds to session and flushes (service-never-commits axiom).

  raise_budget_exceeded_alert(session)
      Inserts a deduped custom/warning alert with
      dedupe_key = llm_budget_exceeded:{YYYY-MM-DD} + ON CONFLICT DO NOTHING.
      Calls session.flush() — never commits.

Security:
  T-05-15: parse_runs row ALWAYS written before signal by the orchestrator (G5
           attribution ordering); this service never re-orders those writes.
  T-05-16: No partial signal is created here; the orchestrator decides not to
           call create_signal_from_extraction on the error path.
  T-05-19: No user-supplied values are interpolated into SQL — only bound params.
"""

from __future__ import annotations

import datetime
import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domains.signals.models import Signal
from app.domains.signals.source_models import ParseRun, RawItem
from app.models.enums import PriceBasis, SignalKind, Urgency
from app.services.grade_service import extract_grade
from app.services.relevance_service import match_product
from parsing.lead_scoring import SCORING_PROMPT_VERSION, compute_lead_score
from parsing.schemas import ExtractionResult, UrgencyLevel
from parsing.schemas import SignalKind as ExtractionKind

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _safe_decimal(value: object) -> decimal.Decimal | None:
    """Coerce value to Decimal, returning None on failure (T-02-15)."""
    if value is None:
        return None
    try:
        d = decimal.Decimal(str(value))
        if not d.is_finite():
            return None
        return d
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None


_URGENCY_MAP: dict[UrgencyLevel | str, Urgency] = {
    UrgencyLevel.LOW: Urgency.low,
    UrgencyLevel.MEDIUM: Urgency.medium,
    UrgencyLevel.HIGH: Urgency.high,
    "low": Urgency.low,
    "medium": Urgency.medium,
    "high": Urgency.high,
}


def _map_urgency(urgency: UrgencyLevel | str | None) -> Urgency | None:
    """Map ExtractionResult.urgency (UrgencyLevel enum) to DB Urgency enum."""
    if urgency is None:
        return None
    return _URGENCY_MAP.get(urgency)


def _map_kind(kind: ExtractionKind | None) -> SignalKind:
    """Map ExtractionResult.kind to DB SignalKind enum.

    WR-07: missing or unrecognized kinds must NOT be coerced to an actionable
    buy/sell direction (the old default of sell_offer fabricated market
    direction). Fall back to the non-directional 'news' kind so an unknown kind
    never invents a buy/sell signal in the feed.
    """
    if kind is None:
        return SignalKind.news  # non-directional fallback (never fabricate buy/sell)
    kind_val = kind.value if hasattr(kind, "value") else str(kind)
    try:
        return SignalKind(kind_val)
    except ValueError:
        return SignalKind.news


def _parse_event_at(result: ExtractionResult, raw_item: RawItem) -> datetime.datetime:
    """Extract event_at from result.event_at → raw_item.event_at → now."""
    if result.event_at:
        try:
            dt = datetime.datetime.fromisoformat(str(result.event_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return dt.astimezone(datetime.UTC)
        except (ValueError, TypeError):
            pass

    if raw_item.event_at is not None:
        return raw_item.event_at

    return datetime.datetime.now(tz=datetime.UTC)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def write_parse_run(
    session: Session,
    raw_item_id: int,
    *,
    parser: str,
    model: str | None,
    prompt_version: str | None,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float | int,
    result: dict[str, object] | None,
    status: str,
    error: str | None,
) -> int:
    """Insert a ParseRun row and flush; return the row id.

    Caller is responsible for the surrounding transaction commit.
    service-never-commits axiom: this function NEVER calls session.commit().

    Args:
        session: Active SQLAlchemy session.
        raw_item_id: FK to raw_items.id.
        parser: Parser discriminator, e.g. 'llm_extract_tools', 'rule_based_fallback'.
        model: LLM model id, or None for rule-based runs.
        prompt_version: Prompt version string, or None for rule-based runs.
        tokens_in: Input tokens consumed (0 for rule-based).
        tokens_out: Output tokens consumed (0 for rule-based).
        latency_ms: Wall-clock LLM latency in milliseconds (0 for rule-based).
        result: JSONB result dict (model output, signal id, or error detail).
        status: 'ok' | 'error' | 'irrelevant'.
        error: Error message, or None on success.

    Returns:
        int: The parse_run id after flush.
    """
    run = ParseRun(
        raw_item_id=raw_item_id,
        parser=parser,
        model=model,
        prompt_version=prompt_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=int(latency_ms) if latency_ms else None,
        result=result,
        status=status,
        error=error,
    )
    session.add(run)
    session.flush()

    logger.debug(
        "ai_signal_service.parse_run_written",
        extra={
            "raw_item_id": raw_item_id,
            "parser": parser,
            "status": status,
            "parse_run_id": run.id,
        },
    )

    return run.id


def create_signal_from_extraction(
    session: Session,
    raw_item: RawItem,
    result: ExtractionResult,
    journal: dict[str, object],
    *,
    needs_review: bool,
) -> Signal:
    """Build a Signal ORM object from an ExtractionResult with ai JSONB stamped.

    Maps ExtractionResult fields to Signal columns, resolves product_id via
    relevance_service.match_product and grade_id via grade_service.extract_grade,
    computes the lead score, and stamps the ai JSONB with the full attribution set.

    The returned Signal is NOT added to the session here — the caller
    (parse_telegram_item task) is responsible for session.add() and flush.

    ai JSONB shape:
        {
          "lead_score": float [0, 1],
          "classification": "HOT" | "MEDIUM" | "LOW",
          "needs_review": bool,
          "model": str | None,
          "prompt_version": str | None,
          "scored_at": ISO-8601 string,
          "scoring_prompt_version": str (SCORING_PROMPT_VERSION constant),
        }

    Security (T-05-15):
        The orchestrator writes the parse_runs row BEFORE calling this function
        (G5 attribution invariant). This service has no awareness of ordering;
        the orchestrator enforces it.

    Args:
        session: Active SQLAlchemy session (used for product/grade lookups).
        raw_item: RawItem ORM object.
        result: Validated ExtractionResult from LLM extractor or rule-based fallback.
        journal: Journal dict from extract_signal (keys: model, prompt_version, …).
        needs_review: True if confidence < CONFIDENCE_REVIEW_THRESHOLD.

    Returns:
        Signal ORM object ready for session.add() + flush.
    """
    # ── Product and grade resolution ─────────────────────────────────────────
    product_id: int | None = match_product(session, result.product or result.grade_text or "")
    grade_text_raw = result.grade_text or result.product or ""
    grade_id, grade_text = extract_grade(grade_text_raw, session)

    # ── Lead scoring ─────────────────────────────────────────────────────────
    score, classification = compute_lead_score(result)

    # ── Timestamps ───────────────────────────────────────────────────────────
    now_iso = datetime.datetime.now(tz=datetime.UTC).isoformat()
    event_at = _parse_event_at(result, raw_item)

    # ── ai JSONB ─────────────────────────────────────────────────────────────
    ai_data: dict[str, object] = {
        "lead_score": score,
        "classification": classification,
        "needs_review": needs_review,
        "model": journal.get("model"),
        "prompt_version": journal.get("prompt_version"),
        "scored_at": now_iso,
        "scoring_prompt_version": SCORING_PROMPT_VERSION,
    }

    # ── Signal ORM construction ───────────────────────────────────────────────
    signal = Signal(
        kind=_map_kind(result.kind),
        source_id=raw_item.source_id,
        raw_item_id=raw_item.id,
        product_id=product_id,
        grade_id=grade_id,
        grade_text=grade_text or result.grade_text,
        volume=_safe_decimal(result.volume),
        volume_unit=result.volume_unit or "MT",
        price=_safe_decimal(result.price),
        currency=result.currency,
        price_basis=PriceBasis.unknown,
        region=result.region,
        destination=None,
        counterparty_id=None,
        counterparty_text=result.counterparty_text,
        urgency=_map_urgency(result.urgency),
        status="new",
        event_at=event_at,
        ai=ai_data,
    )

    logger.debug(
        "ai_signal_service.signal_created",
        extra={
            "raw_item_id": raw_item.id,
            "kind": signal.kind,
            "needs_review": needs_review,
            "lead_score": score,
            "classification": classification,
        },
    )

    return signal


def raise_budget_exceeded_alert(session: Session) -> None:
    """Insert a deduped LLM budget exceeded alert (at most one per UTC day).

    Uses dedupe_key = 'llm_budget_exceeded:{YYYY-MM-DD}' with
    ON CONFLICT (dedupe_key) DO NOTHING to guarantee at most one alert
    per UTC calendar day (mirrors source_health_service pattern, T-02-20).

    Calls session.flush() — never commits (service-never-commits axiom).

    Security (T-05-18):
        Cost-control breach MUST notify. This function is the deduped signal
        that the daily budget has been exhausted. The nightly catch-up and
        rule-based fallback handle pipeline continuity; this alert ensures
        the team is informed.
    """
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    dedupe_key = f"llm_budget_exceeded:{today}"

    session.execute(
        sa.text(
            """
            INSERT INTO alerts (kind, severity, title, body, dedupe_key)
            VALUES (
                'custom',
                'warning',
                :title,
                :body,
                :dedupe_key
            )
            ON CONFLICT (dedupe_key) DO NOTHING
            """
        ),
        {
            "title": "LLM daily token budget exhausted",
            "body": (
                f"The daily LLM token budget has been exhausted ({today}). "
                "Telegram raw items are being processed with rule-based fallback "
                "and will be reprocessed by the nightly_llm_catchup task."
            ),
            "dedupe_key": dedupe_key,
        },
    )
    session.flush()

    logger.warning(
        "ai_signal_service.budget_exceeded_alert",
        extra={"dedupe_key": dedupe_key},
    )
