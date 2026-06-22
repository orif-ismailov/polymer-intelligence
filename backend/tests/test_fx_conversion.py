"""
Tests for fx_service.convert_amount — on-read FX conversion.

Key requirements:
- convert_amount(session, amount, ccy, on_date) returns amount * rate (Decimal)
- Missing rate (no row for ccy/date) → None
- convert_amount MUST NOT write to fx_rates (conversion on read, original preserved)
- REQ-fx-rates: original currency/amount is never mutated

All DB tests use the live-DB guard.
Unit tests mock the session for basic math.
"""

from __future__ import annotations

import datetime
import decimal
import os

import pytest

# ── Live-DB skip guard ────────────────────────────────────────────────────────

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "FX conversion DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


# ── Unit tests with mocked session ──────────────────────────────────────────────

class TestConvertAmountUnit:
    """Unit tests for convert_amount using a mocked DB session."""

    def _make_session_with_rate(
        self, rate: decimal.Decimal | None
    ) -> object:
        """Build a mock session that returns the given rate from execute().fetchone()."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        session = MagicMock()
        mock_row = MagicMock()
        if rate is not None:
            mock_row.__getitem__ = lambda self, idx: rate  # row[0] returns rate
            session.execute.return_value.fetchone.return_value = mock_row
        else:
            session.execute.return_value.fetchone.return_value = None
        return session

    def test_convert_amount_basic_math(self) -> None:
        """convert_amount returns amount * rate."""
        from app.services.fx_service import convert_amount  # noqa: PLC0415

        session = self._make_session_with_rate(decimal.Decimal("12736.68"))
        result = convert_amount(
            session,
            decimal.Decimal("100"),
            "USD",
            datetime.date(2024, 1, 15),
        )

        expected = decimal.Decimal("100") * decimal.Decimal("12736.68")
        assert result == expected, f"Expected {expected}, got {result}"

    def test_convert_amount_missing_rate_returns_none(self) -> None:
        """convert_amount returns None when no rate exists for the ccy/date."""
        from app.services.fx_service import convert_amount  # noqa: PLC0415

        session = self._make_session_with_rate(None)
        result = convert_amount(
            session,
            decimal.Decimal("100"),
            "GBP",
            datetime.date(2024, 1, 15),
        )

        assert result is None, "Missing rate must return None (not raise)"

    def test_convert_amount_returns_decimal(self) -> None:
        """convert_amount result is a Decimal (not float) to preserve money precision."""
        from app.services.fx_service import convert_amount  # noqa: PLC0415

        session = self._make_session_with_rate(decimal.Decimal("12736.68"))
        result = convert_amount(
            session,
            decimal.Decimal("50"),
            "USD",
            datetime.date(2024, 1, 15),
        )

        assert isinstance(result, decimal.Decimal), (
            f"convert_amount must return Decimal, got {type(result)}"
        )

    def test_convert_amount_does_not_write(self) -> None:
        """convert_amount must not call session.execute with INSERT/UPDATE (read-only)."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        session = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: decimal.Decimal("12736.68")
        session.execute.return_value.fetchone.return_value = mock_row

        convert_amount(
            session,
            decimal.Decimal("100"),
            "USD",
            datetime.date(2024, 1, 15),
        )

        # Inspect all calls to session.execute
        for call_args in session.execute.call_args_list:
            sql_text = str(call_args[0][0]).upper()
            assert "INSERT" not in sql_text, "convert_amount must not INSERT"
            assert "UPDATE" not in sql_text, "convert_amount must not UPDATE"
            assert "DELETE" not in sql_text, "convert_amount must not DELETE"


# ── DB-backed tests ────────────────────────────────────────────────────────────

@_requires_real_db
class TestConvertAmountDB:
    """convert_amount integration tests using a migrated seeded DB."""

    @pytest.fixture(scope="class")
    def engine(self):
        import sqlalchemy as sa  # noqa: PLC0415
        return sa.create_engine(_DB_URL, pool_pre_ping=True)

    @pytest.fixture(scope="class")
    def seeded_db(self, engine):
        """Migrate and seed one USD rate for 2024-02-01."""
        import contextlib  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        import sqlalchemy as sa  # noqa: PLC0415
        from alembic.config import Config  # noqa: PLC0415

        from alembic import command as alembic_command  # noqa: PLC0415

        backend_dir = Path(__file__).parent.parent
        alembic_cfg = Config(str(backend_dir / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
        alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")
        alembic_command.upgrade(alembic_cfg, "head")

        # Seed a known FX rate
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO fx_rates (rate_date, ccy, rate)
                    VALUES ('2024-02-01', 'USD', 12800.500000)
                    ON CONFLICT (rate_date, ccy) DO UPDATE SET rate = EXCLUDED.rate
                    """
                )
            )

        yield engine

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")

    def test_convert_amount_exact_date(self, seeded_db) -> None:
        """convert_amount returns correct figure for exact-date rate."""
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        with Session(seeded_db) as session:
            result = convert_amount(
                session,
                decimal.Decimal("100"),
                "USD",
                datetime.date(2024, 2, 1),
            )

        expected = decimal.Decimal("100") * decimal.Decimal("12800.500000")
        assert result == expected

    def test_convert_amount_uses_most_recent_rate(self, seeded_db) -> None:
        """convert_amount uses most-recent rate ≤ on_date (not strictly equal)."""
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        # 2024-02-03 > 2024-02-01 (our only seeded rate) → should still resolve
        with Session(seeded_db) as session:
            result = convert_amount(
                session,
                decimal.Decimal("1"),
                "USD",
                datetime.date(2024, 2, 3),
            )

        assert result is not None, (
            "convert_amount must use the most-recent rate ≤ on_date"
        )
        assert result == decimal.Decimal("1") * decimal.Decimal("12800.500000")

    def test_convert_amount_returns_none_for_future_date_with_no_rate(self, seeded_db) -> None:
        """convert_amount returns None if on_date is before all available rates."""
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        # 2020-01-01 is before any seeded rate → None
        with Session(seeded_db) as session:
            result = convert_amount(
                session,
                decimal.Decimal("100"),
                "USD",
                datetime.date(2020, 1, 1),
            )

        assert result is None, (
            "convert_amount must return None when on_date is before any available rate"
        )

    def test_convert_amount_does_not_mutate_fx_rates(self, seeded_db) -> None:
        """convert_amount does NOT mutate fx_rates rows (original preserved)."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        rate_date = datetime.date(2024, 2, 1)

        # Read the rate BEFORE conversion
        with Session(seeded_db) as session:
            rate_before = session.execute(
                sa.text(
                    "SELECT rate FROM fx_rates WHERE rate_date = :d AND ccy = 'USD'"
                ),
                {"d": rate_date},
            ).scalar()

        # Run conversion
        with Session(seeded_db) as session:
            convert_amount(session, decimal.Decimal("999"), "USD", rate_date)

        # Read the rate AFTER conversion
        with Session(seeded_db) as session:
            rate_after = session.execute(
                sa.text(
                    "SELECT rate FROM fx_rates WHERE rate_date = :d AND ccy = 'USD'"
                ),
                {"d": rate_date},
            ).scalar()

        assert rate_before == rate_after, (
            f"convert_amount must not mutate fx_rates: before={rate_before}, after={rate_after}"
        )

    def test_convert_missing_ccy_returns_none(self, seeded_db) -> None:
        """convert_amount returns None for a ccy with no rates at all."""
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.fx_service import convert_amount  # noqa: PLC0415

        with Session(seeded_db) as session:
            result = convert_amount(
                session,
                decimal.Decimal("100"),
                "XYZ",  # non-existent currency
                datetime.date(2024, 2, 1),
            )

        assert result is None
