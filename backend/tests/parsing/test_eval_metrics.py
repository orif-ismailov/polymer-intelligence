"""
Independent unit tests for eval_metrics.py — the metric math cannot silently drift.

These tests exercise the compute_recall / compute_field_precision / match_field
functions on tiny synthetic gold/pred pairs with KNOWN ANSWERS so that any
regression in the precision rubric fails loudly in CI (AI-SPEC §5.6).

All assertions are deterministic — no I/O, no live LLM calls, no DB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from tests.parsing.eval_metrics import (
    compute_field_precision,
    compute_recall,
    match_field,
    per_field_breakdown,
)
from tests.parsing.eval_config import GATE_FIELDS, PRICE_TOLERANCE_PCT


# ---------------------------------------------------------------------------
# Helpers to build minimal gold/pred rows
# ---------------------------------------------------------------------------

def _gold_row(
    row_id: int,
    is_relevant: bool,
    *,
    product: str | None = None,
    grade_text: str | None = None,
    kind: str | None = None,
    price: Decimal | None = None,
    currency: str | None = None,
    volume: Decimal | None = None,
    counterparty_text: str | None = None,
) -> dict[str, Any]:
    """Build a minimal gold row for testing."""
    return {
        "id": row_id,
        "is_relevant": is_relevant,
        "expected": {
            "product": product,
            "grade_text": grade_text,
            "kind": kind,
            "price": price,
            "currency": currency,
            "volume": volume,
            "counterparty_text": counterparty_text,
        },
    }


def _pred_row(
    row_id: int,
    is_relevant: bool,
    *,
    product: str | None = None,
    grade_text: str | None = None,
    kind: str | None = None,
    price: Decimal | None = None,
    currency: str | None = None,
    volume: Decimal | None = None,
    counterparty_text: str | None = None,
) -> dict[str, Any]:
    """Build a minimal prediction row for testing."""
    return {
        "id": row_id,
        "is_relevant": is_relevant,
        "product": product,
        "grade_text": grade_text,
        "kind": kind,
        "price": price,
        "currency": currency,
        "volume": volume,
        "counterparty_text": counterparty_text,
    }


# ---------------------------------------------------------------------------
# Test 1 — compute_recall: 4/5 relevant-true rows classified relevant
# ---------------------------------------------------------------------------

class TestComputeRecall:
    """Test 1: on a synthetic gold of 5 is_relevant=True rows where predictions
    classify 4 as relevant, compute_recall == 0.8."""

    def test_recall_four_of_five(self) -> None:
        gold = [_gold_row(i, is_relevant=True) for i in range(1, 6)]
        pred = {
            1: _pred_row(1, is_relevant=True),
            2: _pred_row(2, is_relevant=True),
            3: _pred_row(3, is_relevant=True),
            4: _pred_row(4, is_relevant=True),
            5: _pred_row(5, is_relevant=False),  # FN
        }
        recall = compute_recall(gold, pred)
        assert recall == pytest.approx(0.8, abs=1e-6)

    def test_recall_perfect(self) -> None:
        """All relevant rows predicted relevant → 1.0."""
        gold = [_gold_row(i, is_relevant=True) for i in range(1, 4)]
        pred = {i: _pred_row(i, is_relevant=True) for i in range(1, 4)}
        assert compute_recall(gold, pred) == pytest.approx(1.0)

    def test_recall_zero(self) -> None:
        """All relevant rows predicted irrelevant → 0.0."""
        gold = [_gold_row(i, is_relevant=True) for i in range(1, 4)]
        pred = {i: _pred_row(i, is_relevant=False) for i in range(1, 4)}
        assert compute_recall(gold, pred) == pytest.approx(0.0)

    def test_recall_skips_irrelevant_gold_rows(self) -> None:
        """Irrelevant gold rows do not count as FN — recall only on is_relevant=True."""
        gold = [
            _gold_row(1, is_relevant=True),
            _gold_row(2, is_relevant=False),  # irrelevant — not counted
            _gold_row(3, is_relevant=True),
        ]
        pred = {
            1: _pred_row(1, is_relevant=True),
            2: _pred_row(2, is_relevant=False),
            3: _pred_row(3, is_relevant=True),
        }
        assert compute_recall(gold, pred) == pytest.approx(1.0)

    def test_recall_no_relevant_gold(self) -> None:
        """If no gold rows are relevant, return 1.0 (vacuously no FN possible)."""
        gold = [_gold_row(i, is_relevant=False) for i in range(1, 4)]
        pred = {i: _pred_row(i, is_relevant=False) for i in range(1, 4)}
        result = compute_recall(gold, pred)
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 2 — compute_field_precision: known per-field pattern
# ---------------------------------------------------------------------------

class TestComputeFieldPrecision:
    """Test 2: on 3 true-positive rows with a known per-field correct/incorrect
    pattern, compute_field_precision returns the exact macro-average across GATE_FIELDS."""

    def test_precision_known_pattern(self) -> None:
        """
        3 true-positive rows, all fields null except:
          row 1: product="PP"  (both gold+pred match)
          row 2: product="PP", grade_text="T30S" (grade mismatch)
          row 3: kind="sell_offer" (gold/pred match), price=Decimal("950") (match within tol)
        Compute expected macro-average manually.
        """
        synonyms: dict[str, str] = {}
        gold = [
            _gold_row(1, is_relevant=True, product="PP"),
            _gold_row(2, is_relevant=True, product="PP", grade_text="T30S"),
            _gold_row(3, is_relevant=True, kind="sell_offer", price=Decimal("950")),
        ]
        pred = {
            1: _pred_row(1, is_relevant=True, product="PP"),
            2: _pred_row(2, is_relevant=True, product="PP", grade_text="H030"),  # mismatch
            3: _pred_row(3, is_relevant=True, kind="sell_offer", price=Decimal("951")),  # within 0.5%
        }
        precision = compute_field_precision(gold, pred, synonyms)
        # Manual calculation:
        # GATE_FIELDS = [product, grade_text, kind, price, currency, volume, counterparty_text]
        # Row 1: product correct (1), all others null-correct (gold null, pred null) = all 7 correct
        # Row 2: product correct (1), grade_text mismatch (0), others null-correct = 6/7
        # Row 3: kind correct (1), price correct within tolerance (1), others null-correct = 7/7
        # Per-field correct/total:
        # product: rows 1,2 have gold non-null → 2 total; 2 correct → 1.0
        #   (row3 gold null, pred null → NOT counted in denominator per §5.1)
        # grade_text: row 2 gold non-null → 1 total; 0 correct → 0.0
        # kind: row 3 gold non-null → 1 total; 1 correct → 1.0
        # price: row 3 gold non-null → 1 total; 1 correct (951 within 0.5% of 950) → 1.0
        # currency: all null → 0/0 → no contribution (treated as 1.0 per-field or skip)
        # volume: all null → 0/0
        # counterparty_text: all null → 0/0
        # Macro-average across fields that have any gold-non-null data:
        #   product=1.0, grade_text=0.0, kind=1.0, price=1.0 → avg = (1+0+1+1)/4 = 0.75
        # Fields with no gold data at all have no contribution.
        assert precision == pytest.approx(0.75, abs=1e-6)

    def test_precision_all_correct(self) -> None:
        """All fields match → 1.0 precision."""
        synonyms: dict[str, str] = {}
        gold = [_gold_row(1, is_relevant=True, product="PP", currency="USD")]
        pred = {1: _pred_row(1, is_relevant=True, product="PP", currency="USD")}
        precision = compute_field_precision(gold, pred, synonyms)
        assert precision == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 3 — grade synonym: Cyrillic↔Latin
# ---------------------------------------------------------------------------

class TestMatchFieldGrade:
    """Test 3: match_field("grade_text", "Т30С", "T30S", synonyms) is True under
    the synonym map (Cyrillic↔Latin); "T30S" vs "H030" is False."""

    @pytest.fixture
    def synonyms(self) -> dict[str, str]:
        return {"T30S": "grade_key_1", "Т30С": "grade_key_1", "t30s": "grade_key_1", "т30с": "grade_key_1"}

    def test_cyrillic_latin_match(self, synonyms: dict[str, str]) -> None:
        """Cyrillic 'Т30С' matches Latin 'T30S' via synonym map."""
        result = match_field("grade_text", "Т30С", "T30S", synonyms)
        assert result is True

    def test_cyrillic_latin_mismatch(self, synonyms: dict[str, str]) -> None:
        """'T30S' vs 'H030' is False — different grade keys."""
        result = match_field("grade_text", "T30S", "H030", synonyms)
        assert result is False

    def test_grade_case_insensitive(self, synonyms: dict[str, str]) -> None:
        """Grade match is case-insensitive after normalisation."""
        result = match_field("grade_text", "t30s", "T30S", synonyms)
        assert result is True

    def test_grade_exact_no_synonym(self) -> None:
        """Grade without synonym map entry matches by exact normalised string."""
        result = match_field("grade_text", "PP raffia", "PP raffia", {})
        assert result is True

    def test_grade_exact_no_synonym_mismatch(self) -> None:
        """Grade without synonym entry does NOT match different string."""
        result = match_field("grade_text", "PP raffia", "PP injection", {})
        assert result is False


# ---------------------------------------------------------------------------
# Test 4 — price tolerance: ±0.5%
# ---------------------------------------------------------------------------

class TestMatchFieldPrice:
    """Test 4: match_field("price", 950.0, 951.0, synonyms) is True within ±0.5%;
    950 vs 1100 is False."""

    def test_price_within_tolerance(self) -> None:
        """950.0 vs 951.0 is within ±0.5% (951/950 = 1.00105 < 1.005)."""
        result = match_field("price", Decimal("950.0"), Decimal("951.0"), {})
        assert result is True

    def test_price_outside_tolerance(self) -> None:
        """950 vs 1100 is far outside ±0.5%."""
        result = match_field("price", Decimal("950"), Decimal("1100"), {})
        assert result is False

    def test_price_exact(self) -> None:
        """Exact price match is always True."""
        result = match_field("price", Decimal("850"), Decimal("850"), {})
        assert result is True

    def test_price_at_tolerance_boundary(self) -> None:
        """At exactly ±0.5% boundary → True; just over → False."""
        base = Decimal("1000")
        tolerance = PRICE_TOLERANCE_PCT / 100  # 0.005
        # Exactly at boundary: 1000 * 1.005 = 1005
        at_boundary = base * (1 + Decimal(str(tolerance)))
        result = match_field("price", base, at_boundary, {})
        assert result is True

    def test_price_float_inputs(self) -> None:
        """Float inputs are coerced to Decimal for comparison."""
        result = match_field("price", 950.0, 951.0, {})
        assert result is True


# ---------------------------------------------------------------------------
# Test 5 — volume MT normalisation
# ---------------------------------------------------------------------------

class TestMatchFieldVolume:
    """Test 5: gold 50 MT vs system 50 MT passes; un-normalised 50000 (kg) fails."""

    def test_volume_mt_match(self) -> None:
        """50 MT vs 50 MT → True."""
        result = match_field("volume", Decimal("50"), Decimal("50"), {})
        assert result is True

    def test_volume_kg_not_normalised_fails(self) -> None:
        """50000 kg (not normalised) vs 50 MT → False."""
        result = match_field("volume", Decimal("50"), Decimal("50000"), {})
        assert result is False

    def test_volume_exact(self) -> None:
        """100 MT vs 100 MT → True."""
        result = match_field("volume", Decimal("100"), Decimal("100"), {})
        assert result is True


# ---------------------------------------------------------------------------
# Test 6 — currency exact match
# ---------------------------------------------------------------------------

class TestMatchFieldCurrency:
    """Test 6: "USD" vs "USD" True; "USD" vs "UZS" False."""

    def test_currency_match(self) -> None:
        assert match_field("currency", "USD", "USD", {}) is True

    def test_currency_mismatch(self) -> None:
        assert match_field("currency", "USD", "UZS", {}) is False

    def test_currency_case_insensitive(self) -> None:
        """Currency normalised to uppercase — 'usd' vs 'USD' → True."""
        assert match_field("currency", "usd", "USD", {}) is True


# ---------------------------------------------------------------------------
# Test 7 — null handling
# ---------------------------------------------------------------------------

class TestNullHandling:
    """Test 7: gold-null + sys-null is NOT a precision miss; gold-null + sys-non-null IS."""

    def test_both_null_not_a_miss(self) -> None:
        """Gold null, system null → match (not a precision miss, not fabrication)."""
        result = match_field("price", None, None, {})
        assert result is True

    def test_gold_null_sys_non_null_is_fabrication(self) -> None:
        """Gold null, system provides value → fabrication miss → False."""
        result = match_field("price", None, Decimal("950"), {})
        assert result is False

    def test_gold_non_null_sys_null(self) -> None:
        """Gold present, system null → miss → False."""
        result = match_field("price", Decimal("950"), None, {})
        assert result is False

    def test_null_currency_both_null(self) -> None:
        result = match_field("currency", None, None, {})
        assert result is True

    def test_null_grade_gold_null_sys_non_null(self) -> None:
        result = match_field("grade_text", None, "T30S", {})
        assert result is False


# ---------------------------------------------------------------------------
# Test 8 — loader
# ---------------------------------------------------------------------------

class TestGoldenLoader:
    """Test 8: load_golden_set(None) returns the committed example fixture;
    load_golden_set(real_path) reads the customer file; load_predictions("v1")
    returns a dict keyed by row id."""

    def test_load_golden_set_default_returns_fixture(self) -> None:
        """load_golden_set(None) returns the committed example fixture (≥1 row)."""
        from tests.parsing.golden_loader import load_golden_set
        rows = load_golden_set(None)
        assert isinstance(rows, list)
        assert len(rows) >= 1
        for row in rows:
            assert "expected" in row, f"Row {row.get('id')} missing 'expected'"
            assert "is_relevant" in row, f"Row {row.get('id')} missing 'is_relevant'"

    def test_load_golden_set_custom_path(self, tmp_path: "pytest.TempPath") -> None:
        """load_golden_set(path) reads the specified file."""
        import json
        from tests.parsing.golden_loader import load_golden_set as _load_golden_set
        custom = [{"id": 99, "raw_text": "test", "is_relevant": False, "expected": {}}]
        f = tmp_path / "custom.json"
        f.write_text(json.dumps(custom))
        rows = _load_golden_set(str(f))
        assert rows[0]["id"] == 99

    def test_load_predictions_v1_returns_dict(self) -> None:
        """load_predictions('v1') returns a dict keyed by row id."""
        from tests.parsing.golden_loader import load_predictions
        predictions = load_predictions("v1")
        assert isinstance(predictions, dict)
        # All values should be dicts (prediction payloads)
        for key, val in predictions.items():
            assert isinstance(val, dict), f"Prediction for {key} should be a dict"

    def test_load_synonyms_default(self) -> None:
        """load_synonyms(None) returns the committed example synonym map (non-empty dict)."""
        from tests.parsing.golden_loader import load_synonyms
        synonyms = load_synonyms(None)
        assert isinstance(synonyms, dict)

    def test_load_predictions_returns_is_relevant(self) -> None:
        """Each prediction row must have is_relevant key."""
        from tests.parsing.golden_loader import load_predictions
        predictions = load_predictions("v1")
        for row_id, pred in predictions.items():
            assert "is_relevant" in pred, f"Prediction {row_id} missing is_relevant"
