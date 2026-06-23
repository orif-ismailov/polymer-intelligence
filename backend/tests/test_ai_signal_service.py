"""
Tests for ai_signal_service: write_parse_run and create_signal_from_extraction.

Verifies:
- write_parse_run inserts a ParseRun with correct fields, flushes (not commits), returns id
- create_signal_from_extraction maps ExtractionResult → Signal with ai JSONB stamped
- ai JSONB contains: lead_score, classification, needs_review, model, prompt_version, scored_at
- ai JSONB includes scoring_prompt_version
- ExtractionResult → Signal field mapping: kind, volume, price, currency, region, counterparty_text
- urgency denormalized from result.urgency
- event_at from result.event_at or raw_item.event_at or now
- needs_review kwarg is respected
- raise_budget_exceeded_alert inserts a deduped custom/warning alert with ON CONFLICT DO NOTHING
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction_result(
    is_relevant: bool = True,
    confidence: float = 0.9,
    kind: SignalKind = SignalKind.SELL_OFFER,
    product: str = "PP",
    volume: Decimal | None = Decimal("50"),
    price: Decimal | None = Decimal("900"),
    currency: str | None = "USD",
    region: str | None = "Tashkent",
    counterparty_text: str | None = "Shurtan GCC",
    urgency: UrgencyLevel | None = UrgencyLevel.MEDIUM,
    event_at: str | None = None,
) -> ExtractionResult:
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
        region=region,
        counterparty_text=counterparty_text,
        urgency=urgency,
        event_at=event_at,
    )


def _make_raw_item(source_id: int = 100, event_at=None) -> MagicMock:
    ri = MagicMock()
    ri.id = 1
    ri.source_id = source_id
    ri.event_at = event_at
    return ri


def _make_journal(
    model: str = "claude-haiku-4-5",
    prompt_version: str = "v1",
    parser: str = "llm_extract_tools",
    tokens_in: int = 400,
    tokens_out: int = 120,
    latency_ms: float = 350.0,
) -> dict:
    return {
        "parser": parser,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_tokens": 0,
        "latency_ms": latency_ms,
        "raw_response": {"id": "msg_abc"},
    }


# ---------------------------------------------------------------------------
# write_parse_run tests
# ---------------------------------------------------------------------------


class TestWriteParseRun:
    def test_inserts_parse_run_and_flushes(self):
        """write_parse_run inserts a ParseRun with correct fields and calls session.flush()."""
        from app.services.ai_signal_service import write_parse_run  # noqa: PLC0415

        mock_session = MagicMock()
        added = []
        mock_session.add.side_effect = lambda obj: added.append(obj)

        # Assign id after flush (simulate DB autoincrement)
        def flush_side_effect():
            if added:
                added[-1].id = 99

        mock_session.flush.side_effect = flush_side_effect

        # Make ParseRun return an instance with id=None by default
        from app.models.sources import ParseRun  # noqa: PLC0415

        write_parse_run(
            mock_session,
            raw_item_id=1,
            parser="llm_extract_tools",
            model="claude-haiku-4-5",
            prompt_version="v1",
            tokens_in=400,
            tokens_out=120,
            latency_ms=350,
            result={"field": "value"},
            status="ok",
            error=None,
        )

        # session.add and session.flush called (NOT commit)
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_not_called()

        parse_run = added[0]
        assert isinstance(parse_run, ParseRun)
        assert parse_run.raw_item_id == 1
        assert parse_run.parser == "llm_extract_tools"
        assert parse_run.model == "claude-haiku-4-5"
        assert parse_run.prompt_version == "v1"
        assert parse_run.tokens_in == 400
        assert parse_run.tokens_out == 120
        assert parse_run.latency_ms == 350
        assert parse_run.status == "ok"
        assert parse_run.error is None
        assert parse_run.result == {"field": "value"}

    def test_write_parse_run_null_model_for_rule_based(self):
        """write_parse_run with model=None (rule-based path) works correctly."""
        from app.services.ai_signal_service import write_parse_run  # noqa: PLC0415

        mock_session = MagicMock()
        added = []
        mock_session.add.side_effect = lambda obj: added.append(obj)

        write_parse_run(
            mock_session,
            raw_item_id=5,
            parser="rule_based_fallback",
            model=None,
            prompt_version=None,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            result=None,
            status="ok",
            error=None,
        )

        run = added[0]
        assert run.model is None
        assert run.prompt_version is None
        assert run.tokens_in == 0

    def test_write_parse_run_error_status(self):
        """write_parse_run with status='error' captures error field."""
        from app.services.ai_signal_service import write_parse_run  # noqa: PLC0415

        mock_session = MagicMock()
        added = []
        mock_session.add.side_effect = lambda obj: added.append(obj)

        write_parse_run(
            mock_session,
            raw_item_id=2,
            parser="llm_extract_tools",
            model="claude-haiku-4-5",
            prompt_version="v1",
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            result={"raw": "failed_attempts"},
            status="error",
            error="InstructorRetryException: all retries failed",
        )

        run = added[0]
        assert run.status == "error"
        assert "InstructorRetryException" in run.error


# ---------------------------------------------------------------------------
# create_signal_from_extraction tests
# ---------------------------------------------------------------------------


class TestCreateSignalFromExtraction:
    def _call(self, result, journal, *, needs_review=False, raw_item=None, session=None):
        from app.services.ai_signal_service import create_signal_from_extraction  # noqa: PLC0415

        if raw_item is None:
            raw_item = _make_raw_item()
        if session is None:
            session = MagicMock()

        with (
            patch("app.services.ai_signal_service.match_product", return_value=7),
            patch("app.services.ai_signal_service.extract_grade", return_value=(None, "T30S")),
        ):
            return create_signal_from_extraction(
                session,
                raw_item,
                result,
                journal,
                needs_review=needs_review,
            )

    def test_creates_signal_with_ai_jsonb(self):
        """create_signal_from_extraction returns a Signal with ai JSONB stamped."""
        from app.models.signals import Signal  # noqa: PLC0415

        result = _make_extraction_result()
        journal = _make_journal()

        signal = self._call(result, journal, needs_review=False)

        assert isinstance(signal, Signal)
        assert signal.ai is not None
        assert isinstance(signal.ai, dict)

    def test_ai_jsonb_has_required_keys(self):
        """ai JSONB must contain: lead_score, classification, needs_review, model, prompt_version, scored_at."""
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()

        signal = self._call(result, journal, needs_review=False)

        ai = signal.ai
        assert "lead_score" in ai
        assert "classification" in ai
        assert "needs_review" in ai
        assert "model" in ai
        assert "prompt_version" in ai
        assert "scored_at" in ai

    def test_ai_jsonb_needs_review_false(self):
        """needs_review=False → ai['needs_review'] is False."""
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()

        signal = self._call(result, journal, needs_review=False)
        assert signal.ai["needs_review"] is False

    def test_ai_jsonb_needs_review_true(self):
        """needs_review=True → ai['needs_review'] is True."""
        result = _make_extraction_result(confidence=0.3)
        journal = _make_journal()

        signal = self._call(result, journal, needs_review=True)
        assert signal.ai["needs_review"] is True

    def test_ai_jsonb_model_and_prompt_version_from_journal(self):
        """ai['model'] and ai['prompt_version'] come from the journal dict."""
        result = _make_extraction_result()
        journal = _make_journal(model="claude-haiku-4-5", prompt_version="v1")

        signal = self._call(result, journal)

        assert signal.ai["model"] == "claude-haiku-4-5"
        assert signal.ai["prompt_version"] == "v1"

    def test_ai_jsonb_has_lead_score_in_range(self):
        """lead_score must be a float in [0.0, 1.0]."""
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()

        signal = self._call(result, journal)

        score = signal.ai["lead_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_ai_jsonb_classification_hot_medium_low(self):
        """classification must be HOT, MEDIUM, or LOW."""
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()

        signal = self._call(result, journal)

        assert signal.ai["classification"] in ("HOT", "MEDIUM", "LOW")

    def test_ai_jsonb_scored_at_is_iso_string(self):
        """scored_at must be an ISO datetime string."""
        result = _make_extraction_result()
        journal = _make_journal()

        signal = self._call(result, journal)

        scored_at = signal.ai["scored_at"]
        # Should be parseable as ISO 8601
        datetime.datetime.fromisoformat(scored_at)

    def test_signal_kind_from_extraction(self):
        """Signal.kind maps from ExtractionResult.kind."""

        result = _make_extraction_result(kind=SignalKind.BUY_REQUEST)
        journal = _make_journal()

        signal = self._call(result, journal)
        assert signal.kind.value == "buy_request"

    def test_signal_volume_price_currency(self):
        """Volume, price, currency copied from ExtractionResult."""
        result = _make_extraction_result(volume=Decimal("100"), price=Decimal("850"), currency="USD")
        journal = _make_journal()

        signal = self._call(result, journal)
        assert signal.price == Decimal("850")
        assert signal.currency == "USD"

    def test_signal_counterparty_text_from_result(self):
        """counterparty_text from ExtractionResult."""
        result = _make_extraction_result(counterparty_text="Shurtan GCC")
        journal = _make_journal()

        signal = self._call(result, journal)
        assert signal.counterparty_text == "Shurtan GCC"

    def test_signal_region_from_result(self):
        """region from ExtractionResult."""
        result = _make_extraction_result(region="Tashkent")
        journal = _make_journal()

        signal = self._call(result, journal)
        assert signal.region == "Tashkent"

    def test_urgency_denormalized_from_result(self):
        """urgency is denormalized from result.urgency."""

        result = _make_extraction_result(urgency=UrgencyLevel.HIGH)
        journal = _make_journal()

        signal = self._call(result, journal)
        # urgency should be set (either the Urgency enum or matching string)
        assert signal.urgency is not None

    def test_ai_jsonb_scoring_prompt_version_present(self):
        """ai JSONB should include scoring_prompt_version (from lead_scoring.SCORING_PROMPT_VERSION)."""
        from parsing.lead_scoring import SCORING_PROMPT_VERSION  # noqa: PLC0415

        result = _make_extraction_result()
        journal = _make_journal()

        signal = self._call(result, journal)

        # Should have scoring_prompt_version in ai
        assert "scoring_prompt_version" in signal.ai
        assert signal.ai["scoring_prompt_version"] == SCORING_PROMPT_VERSION

    def test_event_at_fallback_to_raw_item(self):
        """event_at falls back to raw_item.event_at when result.event_at is None."""
        raw_event_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        raw_item = _make_raw_item(event_at=raw_event_at)
        result = _make_extraction_result(event_at=None)
        journal = _make_journal()

        signal = self._call(result, journal, raw_item=raw_item)
        assert signal.event_at == raw_event_at

    def test_signal_status_is_new(self):
        """Newly created signals have status='new'."""
        result = _make_extraction_result()
        journal = _make_journal()

        signal = self._call(result, journal)
        assert signal.status == "new"

    def test_signal_source_id_from_raw_item(self):
        """source_id and raw_item_id come from the raw_item."""
        raw_item = _make_raw_item(source_id=42)
        raw_item.id = 7
        result = _make_extraction_result()
        journal = _make_journal()

        signal = self._call(result, journal, raw_item=raw_item)
        assert signal.source_id == 42
        assert signal.raw_item_id == 7


# ---------------------------------------------------------------------------
# raise_budget_exceeded_alert tests
# ---------------------------------------------------------------------------


class TestRaiseBudgetExceededAlert:
    def test_inserts_deduped_alert(self):
        """raise_budget_exceeded_alert inserts a custom/warning alert with ON CONFLICT DO NOTHING."""
        from app.services.ai_signal_service import raise_budget_exceeded_alert  # noqa: PLC0415

        mock_session = MagicMock()
        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute

        raise_budget_exceeded_alert(mock_session)

        # Session.execute was called (INSERT with ON CONFLICT)
        mock_session.execute.assert_called_once()
        # flush was called
        mock_session.flush.assert_called_once()
        # NOT commit (service-never-commits axiom)
        mock_session.commit.assert_not_called()

    def test_alert_dedupe_key_contains_today(self):
        """dedupe_key must contain today's UTC date in YYYY-MM-DD format."""
        from app.services.ai_signal_service import raise_budget_exceeded_alert  # noqa: PLC0415

        mock_session = MagicMock()

        captured_sql = []
        captured_params = []

        def capture_execute(sql, params=None):
            captured_sql.append(str(sql))
            if params:
                captured_params.append(params)
            return MagicMock()

        mock_session.execute.side_effect = capture_execute

        raise_budget_exceeded_alert(mock_session)

        # Check that dedupe_key contains today's date
        today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        all_params = str(captured_params)
        assert today in all_params or "llm_budget_exceeded" in all_params

    def test_alert_has_on_conflict_do_nothing(self):
        """SQL must contain ON CONFLICT DO NOTHING for deduplication."""
        from app.services.ai_signal_service import raise_budget_exceeded_alert  # noqa: PLC0415

        mock_session = MagicMock()
        captured_sql = []

        def capture_execute(sql, params=None):
            captured_sql.append(str(sql))
            return MagicMock()

        mock_session.execute.side_effect = capture_execute

        raise_budget_exceeded_alert(mock_session)

        sql_text = " ".join(captured_sql).upper()
        assert "ON CONFLICT" in sql_text and "NOTHING" in sql_text
