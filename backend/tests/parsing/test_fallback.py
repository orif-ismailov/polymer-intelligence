"""
Tests for parsing.fallback — rule_based_extract().

No live DB or LLM calls — fallback is purely regex-based.

Test coverage:
  4. rule_based_extract("Продам ПП T30S 50 тонн по 950 у.е.") → is_relevant=True,
     product="PP", currency="USD", volume≈50, confidence < CONFIDENCE_REVIEW_THRESHOLD
  5. rule_based_extract("спам реклама подпишись") → is_relevant=False, all market fields null
"""

from __future__ import annotations

from parsing.schemas import CONFIDENCE_REVIEW_THRESHOLD, ExtractionResult


class TestRuleBasedExtractRelevant:
    """Test 4: rule_based_extract on a relevant polymer trade message."""

    def test_pp_sell_offer_extraction(self) -> None:
        """Standard PP sell offer in Russian with у.е. currency."""
        from parsing.fallback import rule_based_extract

        text = "Продам ПП T30S 50 тонн по 950 у.е."
        result = rule_based_extract(text)

        # Must return a valid ExtractionResult
        assert isinstance(result, ExtractionResult), "Must return ExtractionResult"

        # Must be marked relevant
        assert result.is_relevant is True

        # Product must be PP (from ПП)
        assert result.product is not None
        assert result.product.upper() == "PP", f"Expected product=PP, got {result.product!r}"

        # Currency must be USD (from у.е.)
        assert result.currency == "USD", f"Expected currency=USD, got {result.currency!r}"

        # Volume must be approximately 50 MT
        assert result.volume is not None, "Volume should be extracted from '50 тонн'"
        assert abs(float(result.volume) - 50.0) < 1.0, (
            f"Expected volume≈50, got {result.volume}"
        )

        # Confidence must be LOW (below the CONFIDENCE_REVIEW_THRESHOLD)
        # Rule-based is the budget-degraded path — always needs_review (AI-SPEC G4)
        assert result.confidence < CONFIDENCE_REVIEW_THRESHOLD, (
            f"Rule-based confidence must be < {CONFIDENCE_REVIEW_THRESHOLD}, "
            f"got {result.confidence} — rule-based results must always route to needs_review"
        )

    def test_hdpe_buy_request_extraction(self) -> None:
        """HDPE buy request with USD price."""
        from parsing.fallback import rule_based_extract

        text = "Куплю HDPE 2420D 20 тонн 920 долларов"
        result = rule_based_extract(text)

        assert isinstance(result, ExtractionResult)
        assert result.is_relevant is True
        assert result.product is not None
        assert "HDPE" in result.product.upper() or result.product.upper() == "HDPE"
        assert result.confidence < CONFIDENCE_REVIEW_THRESHOLD

    def test_result_validates_against_extraction_result_schema(self) -> None:
        """ExtractionResult.model_validate passes (irrelevant_fields_must_be_null etc.)."""
        from parsing.fallback import rule_based_extract

        text = "Продам ПП T30S 50 тонн по 950 у.е."
        result = rule_based_extract(text)

        # Re-validate — must not raise
        validated = ExtractionResult.model_validate(result.model_dump())
        assert validated.is_relevant is True


class TestRuleBasedExtractIrrelevant:
    """Test 5: rule_based_extract on spam/irrelevant text."""

    def test_spam_returns_irrelevant_with_null_market_fields(self) -> None:
        """Spam text returns is_relevant=False with all market fields null."""
        from parsing.fallback import rule_based_extract

        text = "спам реклама подпишись"
        result = rule_based_extract(text)

        assert isinstance(result, ExtractionResult)
        assert result.is_relevant is False

        # ALL market fields must be null (irrelevant_fields_must_be_null invariant)
        assert result.kind is None, f"kind must be null for irrelevant, got {result.kind}"
        assert result.product is None, f"product must be null for irrelevant, got {result.product}"
        assert result.grade_text is None
        assert result.volume is None
        assert result.price is None
        assert result.currency is None
        assert result.counterparty_text is None
        assert result.urgency is None

    def test_off_topic_returns_irrelevant(self) -> None:
        """Off-topic message returns irrelevant."""
        from parsing.fallback import rule_based_extract

        text = "Привет! Как дела? Погода хорошая сегодня."
        result = rule_based_extract(text)

        assert result.is_relevant is False

    def test_irrelevant_result_validates(self) -> None:
        """Irrelevant result passes ExtractionResult.model_validate (no null violation)."""
        from parsing.fallback import rule_based_extract

        text = "subscribe to our channel for daily updates"
        result = rule_based_extract(text)

        assert result.is_relevant is False
        # Re-validate: the irrelevant_fields_must_be_null validator must not raise
        validated = ExtractionResult.model_validate(result.model_dump())
        assert validated.is_relevant is False

    def test_empty_text_returns_irrelevant(self) -> None:
        """Empty text returns irrelevant (edge case)."""
        from parsing.fallback import rule_based_extract

        result = rule_based_extract("")
        assert result.is_relevant is False
