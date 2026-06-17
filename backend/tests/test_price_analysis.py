"""
Tests for app.services.price_analysis_service.compute_price_analysis.

TDD RED phase: these tests are written BEFORE the implementation.
They will fail until price_analysis_service.py is created.

D-02 spec: target price vs. market average from price_points (market='UZ').
Returns:
  - None if target_price is None.
  - None if no price_points row exists for the product+market='UZ'.
  - dict with target_price, market_avg, delta_pct (signed, 1dp), label.
"""

from __future__ import annotations

import decimal
from unittest.mock import MagicMock


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _make_mock_db() -> MagicMock:
    """Return a MagicMock that quacks like a SQLAlchemy Session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    return db


def _mock_price_row(price_avg: float = 1000.0) -> MagicMock:
    """Return a row mock with price_avg and currency attributes."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: price_avg if idx == 0 else "USD"
    return row


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestComputePriceAnalysis:
    """compute_price_analysis returns None or a price comparison dict."""

    def test_returns_none_when_target_price_is_none(self):
        """Returns None when target_price is None (buyer didn't specify a price)."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        result = compute_price_analysis(db, product_id=1, target_price=None, currency="USD")

        assert result is None

    def test_returns_none_when_no_price_points_row(self):
        """Returns None when price_points has no row for this product+market='UZ'."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        mock_execute_result = MagicMock()
        mock_execute_result.fetchone.return_value = None  # no row
        db.execute.return_value = mock_execute_result

        result = compute_price_analysis(
            db, product_id=1, target_price=decimal.Decimal("1200.0"), currency="USD"
        )

        assert result is None

    def test_target_above_market_returns_positive_delta(self):
        """target_price > market_avg gives positive delta_pct and 'above' label."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        market_avg = decimal.Decimal("1000.0")
        target = decimal.Decimal("1100.0")  # 10% above

        mock_execute_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: market_avg if idx == 0 else "USD"
        mock_execute_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_execute_result

        result = compute_price_analysis(db, product_id=1, target_price=target, currency="USD")

        assert result is not None
        assert result["target_price"] == float(target)
        assert result["market_avg"] == float(market_avg)
        assert result["delta_pct"] == 10.0
        assert "above" in result["label"]

    def test_target_below_market_returns_negative_delta(self):
        """target_price < market_avg gives negative delta_pct and 'below' label."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        market_avg = decimal.Decimal("1000.0")
        target = decimal.Decimal("900.0")   # 10% below

        mock_execute_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: market_avg if idx == 0 else "USD"
        mock_execute_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_execute_result

        result = compute_price_analysis(db, product_id=1, target_price=target, currency="USD")

        assert result is not None
        assert result["delta_pct"] == -10.0
        assert "below" in result["label"]

    def test_delta_pct_rounded_to_one_decimal(self):
        """delta_pct is rounded to 1 decimal place."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        # 1000 / 300 gives 3.333... — should round to 3.3% delta
        market_avg = decimal.Decimal("300.0")
        target = decimal.Decimal("310.0")  # (10/300)*100 = 3.333...

        mock_execute_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: market_avg if idx == 0 else "USD"
        mock_execute_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_execute_result

        result = compute_price_analysis(db, product_id=1, target_price=target, currency="USD")

        assert result is not None
        # delta_pct should be rounded to 1 decimal place
        delta_str = str(result["delta_pct"])
        decimal_parts = delta_str.split(".")
        if len(decimal_parts) > 1:
            assert len(decimal_parts[1]) <= 1, (
                f"delta_pct={result['delta_pct']} has more than 1 decimal place"
            )

    def test_result_contains_all_required_fields(self):
        """Result dict contains target_price, market_avg, delta_pct, label."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        market_avg = decimal.Decimal("1000.0")
        target = decimal.Decimal("1050.0")

        mock_execute_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: market_avg if idx == 0 else "USD"
        mock_execute_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_execute_result

        result = compute_price_analysis(db, product_id=1, target_price=target, currency="USD")

        assert result is not None
        assert "target_price" in result
        assert "market_avg" in result
        assert "delta_pct" in result
        assert "label" in result

    def test_query_uses_price_points_and_market_uz(self):
        """The SQL query selects FROM price_points with market='UZ'."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415
        import inspect

        source = inspect.getsource(compute_price_analysis)
        assert "price_points" in source, "Function must query price_points table"
        assert "'UZ'" in source or "UZ" in source, "Function must filter market='UZ'"

    def test_never_commits(self):
        """compute_price_analysis is read-only — never calls db.commit()."""
        from app.services.price_analysis_service import compute_price_analysis  # noqa: PLC0415

        db = _make_mock_db()
        mock_execute_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: decimal.Decimal("1000.0") if idx == 0 else "USD"
        mock_execute_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_execute_result

        compute_price_analysis(
            db, product_id=1, target_price=decimal.Decimal("1100.0"), currency="USD"
        )

        db.commit.assert_not_called()
