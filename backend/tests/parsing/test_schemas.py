"""
Tests for parsing.schemas — ExtractionResult, SignalKind, UrgencyLevel, validators.

Covers behaviors 1–5 from 05-01-PLAN.md Task 1.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError


class TestExtractionResultValidation:
    """Test 1: ExtractionResult.model_validate(full valid sell_offer dict) succeeds."""

    def test_full_valid_sell_offer(self) -> None:
        """A complete sell_offer dict validates without error and coerces Decimal fields."""
        from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel

        data = {
            "is_relevant": True,
            "kind": "sell_offer",
            "product": "PP",
            "grade_text": "T30S raffia",
            "volume": "50",
            "volume_unit": "MT",
            "price": "850.00",
            "currency": "USD",
            "region": "Tashkent",
            "counterparty_text": "Shurtan GCC",
            "urgency": "high",
            "lead_score": 0.9,
            "confidence": 0.95,
            "field_confidence": {
                "product": 1.0,
                "grade_text": 0.9,
                "volume": 1.0,
                "price": 1.0,
                "currency": 1.0,
                "counterparty": 0.8,
                "region": 0.7,
                "urgency": 0.9,
            },
            "event_at": None,
            "is_forwarded": False,
        }
        result = ExtractionResult.model_validate(data)
        assert result.is_relevant is True
        assert result.kind == SignalKind.SELL_OFFER
        assert result.product == "PP"
        assert result.grade_text == "T30S raffia"
        # Decimal coercion
        assert isinstance(result.volume, Decimal)
        assert result.volume == Decimal("50")
        assert isinstance(result.price, Decimal)
        assert result.price == Decimal("850.00")
        assert result.currency == "USD"
        assert result.urgency == UrgencyLevel.HIGH
        assert result.confidence == 0.95
        assert result.is_forwarded is False


class TestIrrelevantFieldsMustBeNull:
    """Test 2: is_relevant=False with non-null market fields raises ValidationError."""

    def test_irrelevant_with_product_raises(self) -> None:
        """is_relevant=False but product='PP' must raise ValidationError."""
        from parsing.schemas import ExtractionResult

        with pytest.raises(ValidationError) as exc_info:
            ExtractionResult.model_validate({
                "is_relevant": False,
                "kind": None,
                "product": "PP",
                "grade_text": None,
                "volume": None,
                "price": None,
                "currency": None,
                "region": None,
                "counterparty_text": None,
                "urgency": None,
                "lead_score": None,
                "confidence": 0.3,
            })
        # Error message mentions the non-null field
        assert "product" in str(exc_info.value).lower()

    def test_irrelevant_all_null_succeeds(self) -> None:
        """is_relevant=False with all market fields null is valid."""
        from parsing.schemas import ExtractionResult

        result = ExtractionResult.model_validate({
            "is_relevant": False,
            "kind": None,
            "product": None,
            "grade_text": None,
            "volume": None,
            "price": None,
            "currency": None,
            "region": None,
            "counterparty_text": None,
            "urgency": None,
            "lead_score": None,
            "confidence": 0.1,
        })
        assert result.is_relevant is False
        assert result.kind is None
        assert result.product is None


class TestCurrencyNormalisation:
    """Test 3: currency normalisation and validation."""

    def test_lowercase_usd_normalised(self) -> None:
        """currency='usd' normalises to 'USD'."""
        from parsing.schemas import ExtractionResult

        result = ExtractionResult.model_validate({
            "is_relevant": True,
            "kind": "sell_offer",
            "product": "PP",
            "grade_text": None,
            "volume": "10",
            "price": "900",
            "currency": "usd",
            "region": None,
            "counterparty_text": None,
            "urgency": None,
            "lead_score": None,
            "confidence": 0.8,
        })
        assert result.currency == "USD"

    def test_invalid_currency_raises(self) -> None:
        """currency='DOLLAR' (not a 3-letter code) raises ValidationError."""
        from parsing.schemas import ExtractionResult

        with pytest.raises(ValidationError) as exc_info:
            ExtractionResult.model_validate({
                "is_relevant": True,
                "kind": "sell_offer",
                "product": "HDPE",
                "grade_text": None,
                "volume": "20",
                "price": "950",
                "currency": "DOLLAR",
                "region": None,
                "counterparty_text": None,
                "urgency": None,
                "lead_score": None,
                "confidence": 0.7,
            })
        assert "currency" in str(exc_info.value).lower() or "iso" in str(exc_info.value).lower()

    def test_uzs_currency_accepted(self) -> None:
        """currency='UZS' is a valid 3-letter code."""
        from parsing.schemas import ExtractionResult

        result = ExtractionResult.model_validate({
            "is_relevant": True,
            "kind": "price_quote",
            "product": "PP",
            "grade_text": None,
            "volume": None,
            "price": "9500000",
            "currency": "UZS",
            "region": None,
            "counterparty_text": None,
            "urgency": None,
            "lead_score": None,
            "confidence": 0.85,
        })
        assert result.currency == "UZS"


class TestConfidenceBounds:
    """Test 4: confidence=1.5 raises ValidationError (le=1.0 bound)."""

    def test_confidence_above_1_raises(self) -> None:
        """confidence=1.5 must raise ValidationError."""
        from parsing.schemas import ExtractionResult

        with pytest.raises(ValidationError):
            ExtractionResult.model_validate({
                "is_relevant": True,
                "kind": "sell_offer",
                "product": "PP",
                "grade_text": None,
                "volume": "10",
                "price": "800",
                "currency": "USD",
                "region": None,
                "counterparty_text": None,
                "urgency": None,
                "lead_score": None,
                "confidence": 1.5,  # invalid: le=1.0
            })

    def test_confidence_0_accepted(self) -> None:
        """confidence=0.0 is valid (lower bound)."""
        from parsing.schemas import ExtractionResult

        result = ExtractionResult.model_validate({
            "is_relevant": False,
            "kind": None,
            "product": None,
            "grade_text": None,
            "volume": None,
            "price": None,
            "currency": None,
            "region": None,
            "counterparty_text": None,
            "urgency": None,
            "lead_score": None,
            "confidence": 0.0,
        })
        assert result.confidence == 0.0


class TestEnumParity:
    """Test 5: SignalKind and UrgencyLevel enum .value sets exactly equal app.models.enums."""

    def test_signal_kind_parity_with_db_enum(self) -> None:
        """parsing.schemas.SignalKind values == app.models.enums.SignalKind values."""
        from app.models.enums import SignalKind as DBSignalKind
        from parsing.schemas import SignalKind as ParsingSignalKind

        parsing_values = {e.value for e in ParsingSignalKind}
        db_values = {e.value for e in DBSignalKind}
        assert parsing_values == db_values, (
            f"SignalKind enum mismatch:\n"
            f"  parsing: {sorted(parsing_values)}\n"
            f"  DB:      {sorted(db_values)}"
        )

    def test_urgency_level_parity_with_db_enum(self) -> None:
        """parsing.schemas.UrgencyLevel values == app.models.enums.Urgency values."""
        from app.models.enums import Urgency as DBUrgency
        from parsing.schemas import UrgencyLevel as ParsingUrgency

        parsing_values = {e.value for e in ParsingUrgency}
        db_values = {e.value for e in DBUrgency}
        assert parsing_values == db_values, (
            f"UrgencyLevel enum mismatch:\n"
            f"  parsing: {sorted(parsing_values)}\n"
            f"  DB:      {sorted(db_values)}"
        )


class TestSchemaConstants:
    """Test that CONFIDENCE_REVIEW_THRESHOLD is exported at the expected value."""

    def test_confidence_review_threshold(self) -> None:
        """CONFIDENCE_REVIEW_THRESHOLD is 0.5."""
        from parsing.schemas import CONFIDENCE_REVIEW_THRESHOLD

        assert CONFIDENCE_REVIEW_THRESHOLD == 0.5

    def test_budget_exceeded_is_exception(self) -> None:
        """BudgetExceeded is an Exception subclass."""
        from parsing.schemas import BudgetExceeded

        exc = BudgetExceeded("daily limit hit")
        assert isinstance(exc, Exception)
        assert "daily limit" in str(exc)
