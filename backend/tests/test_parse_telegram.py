"""
Tests for parse_telegram_item Celery task and orchestration flow.

Tests cover the 8 required behaviors from 05-04 PLAN:
1. Happy path: LLM extract → parse_runs ok + signal with ai.needs_review=false
2. needs_review: confidence < 0.5 → signal with ai.needs_review=true
3. irrelevant: is_relevant=False → no signal, parse_runs status=ok/irrelevant
4. Dead-letter: InstructorRetryException → parse_runs error, no signal, task doesn't raise
5. Budget degrade: BudgetExceeded → rule_based_extract, nightly enqueue, budget alert
6. Double-parse guard: already parsed → return immediately, no new parse_runs row
7. Attribution invariant: parse_runs BEFORE signal (G5)
8. Blank text: empty content → irrelevant WITHOUT calling extract_signal (G6)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from parsing.schemas import BudgetExceeded, ExtractionResult, SignalKind, UrgencyLevel

# ---------------------------------------------------------------------------
# Test helpers and fixtures
# ---------------------------------------------------------------------------


def _make_raw_item(
    id_: int = 1,
    source_id: int = 100,
    parse_status: str = "pending",
    content: str | None = "Продаю ПП Т30С 50 тонн, $900/т, у.е. EXW Ташкент",
) -> MagicMock:
    """Return a mock RawItem with sensible defaults."""
    ri = MagicMock()
    ri.id = id_
    ri.source_id = source_id
    ri.parse_status = parse_status
    ri.content = content
    ri.event_at = None
    ri.payload = {}
    return ri


def _make_extraction_result(
    is_relevant: bool = True,
    confidence: float = 0.9,
    kind: SignalKind = SignalKind.SELL_OFFER,
    product: str = "PP",
    volume: Decimal | None = Decimal("50"),
    price: Decimal | None = Decimal("900"),
    currency: str | None = "USD",
    urgency: UrgencyLevel | None = None,
    counterparty_text: str | None = None,
) -> ExtractionResult:
    """Return an ExtractionResult suitable for testing."""
    if not is_relevant:
        return ExtractionResult(is_relevant=False, confidence=0.1)
    return ExtractionResult(
        is_relevant=is_relevant,
        confidence=confidence,
        kind=kind,
        product=product,
        grade_text="T30S",
        volume=volume,
        volume_unit="MT",
        price=price,
        currency=currency,
        region="Tashkent",
        counterparty_text=counterparty_text,
        urgency=urgency,
    )


def _make_journal(
    model: str | None = "claude-haiku-4-5",
    prompt_version: str | None = "v1",
    tokens_in: int = 400,
    tokens_out: int = 120,
    latency_ms: float = 350.0,
    parser: str = "llm_extract_tools",
) -> dict:
    """Return a journal dict as returned by extract_signal."""
    return {
        "parser": parser,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_tokens": 0,
        "latency_ms": latency_ms,
        "raw_response": {},
    }


# ---------------------------------------------------------------------------
# Lazy import helper (task is not importable without patching get_session)
# ---------------------------------------------------------------------------


def _import_task():
    """Import parse_telegram_item and helpers under test."""
    from app.tasks.parse_telegram import (  # noqa: PLC0415
        enqueue_for_telegram_parse,
        parse_telegram_item,
    )
    return parse_telegram_item, enqueue_for_telegram_parse


# ---------------------------------------------------------------------------
# Test 1: Happy path — confidence >= 0.5 → needs_review=false
# ---------------------------------------------------------------------------


def test_happy_path_llm_extract_creates_signal_needs_review_false():
    """parse_telegram_item writes ONE parse_runs row + ONE signal with ai.needs_review=False."""
    raw_item = _make_raw_item()
    result = _make_extraction_result(confidence=0.9)
    journal = _make_journal()

    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    # We'll check parse_runs was added before signal via call order
    added_objects = []
    mock_session.add.side_effect = lambda obj: added_objects.append(type(obj).__name__)

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal", return_value=(result, journal)),
        patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
        patch("app.tasks.parse_telegram.record_actual_tokens"),
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Продаю ПП T30S"),
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42) as mock_write_run,
        patch("app.tasks.parse_telegram.create_signal_from_extraction", return_value=MagicMock()) as mock_create_signal,
        patch("app.tasks.parse_telegram.match_product", return_value=7),
        patch("app.tasks.parse_telegram.extract_grade", return_value=(None, "T30S")),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # parse_runs row written
    mock_write_run.assert_called_once()
    run_kwargs = mock_write_run.call_args
    assert run_kwargs[1].get("status") == "ok" or run_kwargs[0][2] == "ok" or "ok" in str(run_kwargs)

    # signal created with needs_review=False (confidence=0.9 >= 0.5)
    mock_create_signal.assert_called_once()
    # needs_review arg should be False
    signal_kwargs = mock_create_signal.call_args[1]
    assert signal_kwargs.get("needs_review") is False

    # raw_item.parse_status set to 'parsed'
    assert raw_item.parse_status == "parsed"
    mock_session.commit.assert_called()


# ---------------------------------------------------------------------------
# Test 2: needs_review path — confidence < 0.5 → needs_review=true
# ---------------------------------------------------------------------------


def test_low_confidence_sets_needs_review_true():
    """confidence=0.3 → ai.needs_review=True; raw_items.parse_status='parsed'."""
    raw_item = _make_raw_item()
    result = _make_extraction_result(confidence=0.3)
    journal = _make_journal()

    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal", return_value=(result, journal)),
        patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
        patch("app.tasks.parse_telegram.record_actual_tokens"),
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Продаю ПП T30S"),
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42),
        patch("app.tasks.parse_telegram.create_signal_from_extraction", return_value=MagicMock()) as mock_create_signal,
        patch("app.tasks.parse_telegram.match_product", return_value=7),
        patch("app.tasks.parse_telegram.extract_grade", return_value=(None, "T30S")),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # needs_review=True (confidence=0.3 < 0.5)
    mock_create_signal.assert_called_once()
    signal_kwargs = mock_create_signal.call_args[1]
    assert signal_kwargs.get("needs_review") is True
    assert raw_item.parse_status == "parsed"


# ---------------------------------------------------------------------------
# Test 3: Irrelevant — is_relevant=False → no signal
# ---------------------------------------------------------------------------


def test_irrelevant_result_no_signal_written():
    """ExtractionResult(is_relevant=False) → no signal, parse_runs ok/irrelevant."""
    raw_item = _make_raw_item()
    result = _make_extraction_result(is_relevant=False)
    journal = _make_journal()

    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal", return_value=(result, journal)),
        patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
        patch("app.tasks.parse_telegram.record_actual_tokens"),
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Скидки на услуги доставки"),
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42) as mock_write_run,
        patch("app.tasks.parse_telegram.create_signal_from_extraction") as mock_create_signal,
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # No signal created
    mock_create_signal.assert_not_called()
    # parse_runs written
    mock_write_run.assert_called_once()
    # parse_status set to irrelevant
    assert raw_item.parse_status == "irrelevant"


# ---------------------------------------------------------------------------
# Test 4: Dead-letter — InstructorRetryException → parse_runs error, no signal
# ---------------------------------------------------------------------------


def test_instructor_retry_exception_dead_letters():
    """InstructorRetryException → parse_runs.status='error' + parse_status='failed', no signal, no crash."""
    from instructor.core import InstructorRetryException  # noqa: PLC0415

    raw_item = _make_raw_item()
    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    exc = InstructorRetryException(
        "All retries failed",
        n_attempts=2,
        total_usage=0,
        last_completion=None,
        messages=[],
    )

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal", side_effect=exc),
        patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Продаю ПП"),
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42) as mock_write_run,
        patch("app.tasks.parse_telegram.create_signal_from_extraction") as mock_create_signal,
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        # Must NOT raise (worker survives)
        parse_telegram_item(1)

    # No signal created (G3)
    mock_create_signal.assert_not_called()
    # parse_runs row with error status
    mock_write_run.assert_called_once()
    write_kwargs = mock_write_run.call_args[1]
    assert write_kwargs.get("status") == "error"
    # parse_status='failed'
    assert raw_item.parse_status == "failed"


# ---------------------------------------------------------------------------
# Test 5: Budget degrade — BudgetExceeded → rule_based_extract + nightly + alert
# ---------------------------------------------------------------------------


def test_budget_exceeded_degrades_to_rule_based():
    """BudgetExceeded → rule_based_extract used, nightly reprocess enqueued, budget alert raised."""
    raw_item = _make_raw_item()
    # rule_based result has confidence < 0.5 (always needs_review per 05-03)
    rule_result = _make_extraction_result(confidence=0.4)

    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.check_and_reserve_tokens", side_effect=BudgetExceeded("exhausted")),
        patch("app.tasks.parse_telegram.rule_based_extract", return_value=rule_result) as mock_rule_extract,
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Продаю ПП"),
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42),
        patch("app.tasks.parse_telegram.create_signal_from_extraction", return_value=MagicMock()) as mock_create_signal,
        patch("app.tasks.parse_telegram.enqueue_nightly_reprocess") as mock_nightly,
        patch("app.tasks.parse_telegram.raise_budget_exceeded_alert") as mock_alert,
        patch("app.tasks.parse_telegram.match_product", return_value=7),
        patch("app.tasks.parse_telegram.extract_grade", return_value=(None, "T30S")),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # rule-based fallback was used
    mock_rule_extract.assert_called_once()
    # nightly reprocess enqueued
    mock_nightly.assert_called_once()
    # budget alert raised
    mock_alert.assert_called_once()
    # Signal was created (rule-based still produces a signal but with needs_review=True)
    mock_create_signal.assert_called_once()
    signal_kwargs = mock_create_signal.call_args[1]
    assert signal_kwargs.get("needs_review") is True


# ---------------------------------------------------------------------------
# Test 6: Double-parse guard — already parsed → no new parse_runs row
# ---------------------------------------------------------------------------


def test_already_parsed_returns_immediately():
    """parse_status != 'pending' → return immediately, no parse_runs row, no extract_signal."""
    raw_item = _make_raw_item(parse_status="parsed")
    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal") as mock_extract,
        patch("app.tasks.parse_telegram.write_parse_run") as mock_write_run,
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # No LLM call, no parse_runs row
    mock_extract.assert_not_called()
    mock_write_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: Attribution invariant — parse_runs BEFORE signal (G5)
# ---------------------------------------------------------------------------


def test_attribution_invariant_parse_run_before_signal():
    """G5: write_parse_run is called BEFORE create_signal_from_extraction."""
    raw_item = _make_raw_item()
    result = _make_extraction_result(confidence=0.9)
    journal = _make_journal()

    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    call_order = []

    def mock_write_run(*args, **kwargs):
        call_order.append("parse_run")
        return 42

    def mock_create_signal(*args, **kwargs):
        call_order.append("signal")
        return MagicMock()

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.extract_signal", return_value=(result, journal)),
        patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
        patch("app.tasks.parse_telegram.record_actual_tokens"),
        patch("app.tasks.parse_telegram.prepare_message_text", return_value="Продаю ПП"),
        patch("app.tasks.parse_telegram.write_parse_run", side_effect=mock_write_run),
        patch("app.tasks.parse_telegram.create_signal_from_extraction", side_effect=mock_create_signal),
        patch("app.tasks.parse_telegram.match_product", return_value=7),
        patch("app.tasks.parse_telegram.extract_grade", return_value=(None, "T30S")),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # parse_run MUST come first (G5 attribution invariant)
    assert call_order[0] == "parse_run", f"Expected parse_run first, got: {call_order}"
    assert "signal" in call_order


# ---------------------------------------------------------------------------
# Test 8: Blank text — G6 cost guard, no LLM call
# ---------------------------------------------------------------------------


def test_blank_content_marked_irrelevant_without_llm_call():
    """Empty/blank content → marked irrelevant WITHOUT calling extract_signal (G6)."""
    raw_item = _make_raw_item(content="")
    mock_session = MagicMock()
    mock_session.get.return_value = raw_item

    with (
        patch("app.tasks.parse_telegram.get_session") as mock_get_session,
        patch("app.tasks.parse_telegram.prepare_message_text", return_value=""),
        patch("app.tasks.parse_telegram.extract_signal") as mock_extract,
        patch("app.tasks.parse_telegram.check_and_reserve_tokens") as mock_budget,
        patch("app.tasks.parse_telegram.write_parse_run", return_value=42) as mock_write_run,
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        parse_telegram_item, _ = _import_task()
        parse_telegram_item(1)

    # No LLM call (G6 — cost guard)
    mock_extract.assert_not_called()
    # No budget reservation (would be wasteful + BudgetExceeded risk)
    mock_budget.assert_not_called()
    # parse_runs row still written (to journal the blank decision)
    mock_write_run.assert_called_once()
    # parse_status irrelevant
    assert raw_item.parse_status == "irrelevant"


# ---------------------------------------------------------------------------
# Test: enqueue_for_telegram_parse helper exists and dispatches
# ---------------------------------------------------------------------------


def test_enqueue_for_telegram_parse_dispatches():
    """enqueue_for_telegram_parse(id) dispatches parse_telegram_item.delay(id)."""
    with patch("app.tasks.parse_telegram.parse_telegram_item") as mock_task:
        mock_delay = MagicMock()
        mock_task.delay = mock_delay

        _, enqueue_for_telegram_parse = _import_task()
        enqueue_for_telegram_parse(99)

    mock_delay.assert_called_once_with(99)
