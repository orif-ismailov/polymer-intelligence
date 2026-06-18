"""
Tests for parsing.lead_scoring — compute_lead_score() + SCORING_PROMPT_VERSION.

No live LLM calls — scoring is deterministic rules-based.

Test coverage:
  6. compute_lead_score on a high-volume HOT-language result → score≥0.7, class="HOT"
     A routine price_quote result → "LOW"
     The returned tuple carries SCORING_PROMPT_VERSION
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel


def _make_hot_result() -> ExtractionResult:
    """High-volume sell_offer with urgency — expected HOT classification."""
    return ExtractionResult(
        is_relevant=True,
        kind=SignalKind.SELL_OFFER,
        product="PP",
        grade_text="T30S",
        volume=Decimal("500"),       # large volume
        volume_unit="MT",
        price=Decimal("950"),
        currency="USD",
        region=None,
        counterparty_text="Shurtan GCC",
        urgency=UrgencyLevel.HIGH,   # high urgency language
        lead_score=None,
        confidence=0.9,
    )


def _make_low_result() -> ExtractionResult:
    """Routine price_quote with no volume/counterparty — expected LOW classification."""
    return ExtractionResult(
        is_relevant=True,
        kind=SignalKind.PRICE_QUOTE,
        product="PVC",
        grade_text=None,
        volume=None,                 # no volume
        volume_unit="MT",
        price=Decimal("1100"),
        currency="UZS",
        region=None,
        counterparty_text=None,     # no counterparty
        urgency=UrgencyLevel.LOW,
        lead_score=None,
        confidence=0.7,
    )


def _make_buy_request() -> ExtractionResult:
    """Buy request with volume — should score reasonably."""
    return ExtractionResult(
        is_relevant=True,
        kind=SignalKind.BUY_REQUEST,
        product="HDPE",
        grade_text="2420D",
        volume=Decimal("50"),
        volume_unit="MT",
        price=Decimal("920"),
        currency="USD",
        region=None,
        counterparty_text=None,
        urgency=UrgencyLevel.MEDIUM,
        lead_score=None,
        confidence=0.8,
    )


class TestComputeLeadScore:
    """Test 6: compute_lead_score returns (score, classification) with SCORING_PROMPT_VERSION."""

    def test_hot_result_scores_high(self) -> None:
        """High-volume sell_offer with urgency=HIGH scores ≥0.7 → HOT."""
        from parsing.lead_scoring import SCORING_PROMPT_VERSION, compute_lead_score

        result = _make_hot_result()
        score, classification = compute_lead_score(result)

        assert isinstance(score, float), f"score must be float, got {type(score)}"
        assert 0.0 <= score <= 1.0, f"score must be in [0,1], got {score}"
        assert score >= 0.7, f"High-urgency high-volume result should score ≥0.7, got {score}"
        assert classification == "HOT", f"Expected HOT, got {classification!r}"

    def test_price_quote_scores_low(self) -> None:
        """Routine price_quote with no volume/counterparty/urgency scores LOW."""
        from parsing.lead_scoring import compute_lead_score

        result = _make_low_result()
        score, classification = compute_lead_score(result)

        assert classification == "LOW", f"Expected LOW for routine price quote, got {classification!r}"
        assert score < 0.4, f"Routine price quote should score < 0.4, got {score}"

    def test_scoring_prompt_version_constant_defined(self) -> None:
        """SCORING_PROMPT_VERSION must be defined and non-empty."""
        from parsing.lead_scoring import SCORING_PROMPT_VERSION

        assert isinstance(SCORING_PROMPT_VERSION, str)
        assert SCORING_PROMPT_VERSION, "SCORING_PROMPT_VERSION must be non-empty"

    def test_classification_hot_threshold(self) -> None:
        """classify(0.75) → HOT; classify(0.45) → MEDIUM; classify(0.2) → LOW."""
        from parsing.lead_scoring import classify

        assert classify(0.75) == "HOT"
        assert classify(0.7) == "HOT"      # exactly at HOT threshold
        assert classify(0.69) == "MEDIUM"  # just below HOT
        assert classify(0.45) == "MEDIUM"
        assert classify(0.4) == "MEDIUM"   # exactly at MEDIUM threshold
        assert classify(0.39) == "LOW"     # just below MEDIUM
        assert classify(0.2) == "LOW"
        assert classify(0.0) == "LOW"

    def test_score_range_is_zero_to_one(self) -> None:
        """compute_lead_score always returns score in [0.0, 1.0]."""
        from parsing.lead_scoring import compute_lead_score

        for result in [_make_hot_result(), _make_low_result(), _make_buy_request()]:
            score, classification = compute_lead_score(result)
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
            assert classification in {"HOT", "MEDIUM", "LOW"}, (
                f"Invalid classification: {classification}"
            )

    def test_deal_kind_scores_high(self) -> None:
        """A deal kind is a higher-quality signal and should score above LOW."""
        from parsing.lead_scoring import compute_lead_score

        deal_result = ExtractionResult(
            is_relevant=True,
            kind=SignalKind.DEAL,
            product="PP",
            grade_text="T30S",
            volume=Decimal("100"),
            volume_unit="MT",
            price=Decimal("900"),
            currency="USD",
            region=None,
            counterparty_text="Shurtan",
            urgency=UrgencyLevel.HIGH,
            lead_score=None,
            confidence=0.95,
        )
        score, classification = compute_lead_score(deal_result)
        # A deal with volume, price, and counterparty should score above LOW
        assert classification in {"HOT", "MEDIUM"}, (
            f"A deal with full fields should not score LOW, got {classification}"
        )
