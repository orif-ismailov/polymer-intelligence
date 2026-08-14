"""
Tests for the CBU rates adapter (app.ingest.cbu_rates.adapter) and
the fetch_cbu_rates Celery task (app.tasks.ingest_cbu).

Test categories:
1. Unit tests: parse a CBU JSON sample → expected (rate_date, ccy, rate) rows
2. Adapter registration: get_adapter("cbu_rates") succeeds
3. DB-backed tests (live-DB guard): upsert_fx_rates idempotency

Run with live DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_cbu_rates.py -v
"""

from __future__ import annotations

import contextlib
import datetime
import decimal
import json
import os
from pathlib import Path

import pytest

# ── Live-DB skip guard ────────────────────────────────────────────────────────

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "CBU rates DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)

# ── Sample CBU JSON fixture ───────────────────────────────────────────────────

# A representative sample of the CBU JSON API response
# https://cbu.uz/ru/arkhiv-kursov-valyut/json/
CBU_SAMPLE = json.dumps([
    {
        "id": "67",
        "Code": "840",
        "Ccy": "USD",
        "CcyNm_RU": "Доллар США",
        "CcyNm_UZ": "AQSH dollari",
        "CcyNm_UZC": "АҚШ доллари",
        "CcyNm_EN": "US Dollar",
        "Nominal": "1",
        "Rate": "12736.68",
        "Diff": "8.93",
        "Date": "2024-01-15"
    },
    {
        "id": "156",
        "Code": "156",
        "Ccy": "CNY",
        "CcyNm_RU": "Китайский юань",
        "CcyNm_UZ": "Xitoy yuani",
        "CcyNm_UZC": "Хитой юани",
        "CcyNm_EN": "Chinese Yuan",
        "Nominal": "1",
        "Rate": "1766.32",
        "Diff": "-1.23",
        "Date": "2024-01-15"
    },
    {
        "id": "643",
        "Code": "643",
        "Ccy": "RUB",
        "CcyNm_RU": "Российский рубль",
        "CcyNm_UZ": "Rossiya rubli",
        "CcyNm_UZC": "Россия рубли",
        "CcyNm_EN": "Russian Ruble",
        "Nominal": "1",
        "Rate": "143.19",
        "Diff": "0.52",
        "Date": "2024-01-15"
    },
])

CBU_EXPECTED_DATE = datetime.date(2024, 1, 15)
CBU_EXPECTED_ROWS = [
    ("USD", decimal.Decimal("12736.68")),
    ("CNY", decimal.Decimal("1766.32")),
    ("RUB", decimal.Decimal("143.19")),
]

# Malformed sample: one row has a non-numeric Rate
CBU_MALFORMED_SAMPLE = json.dumps([
    {
        "Ccy": "USD",
        "Rate": "12736.68",
        "Date": "2024-01-15"
    },
    {
        "Ccy": "EUR",
        "Rate": "not_a_number",  # malformed
        "Date": "2024-01-15"
    },
    {
        "Ccy": "CNY",
        "Rate": "1766.32",
        "Date": "2024-01-15"
    },
])


# ── Unit tests: parsing ────────────────────────────────────────────────────────

class TestCbuJsonParsing:
    """CbuRatesAdapter._parse_cbu_json correctly extracts (rate_date, ccy, rate) rows."""

    def test_parse_cbu_json_returns_expected_rows(self) -> None:
        """Parsing the sample CBU JSON yields the expected (date, ccy, rate) tuples."""
        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        rows = adapter._parse_cbu_json(CBU_SAMPLE)

        assert len(rows) == 3
        for row in rows:
            assert row.rate_date == CBU_EXPECTED_DATE

        ccy_rates = {r.ccy: r.rate for r in rows}
        for ccy, expected_rate in CBU_EXPECTED_ROWS:
            assert ccy in ccy_rates, f"Expected ccy {ccy!r} in parsed rows"
            assert ccy_rates[ccy] == expected_rate, (
                f"Rate mismatch for {ccy}: {ccy_rates[ccy]} != {expected_rate}"
            )

    def test_parse_skips_malformed_rate(self) -> None:
        """Malformed Rate values are skipped; valid rows are still returned (T-02-15)."""
        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        rows = adapter._parse_cbu_json(CBU_MALFORMED_SAMPLE)

        # EUR has "not_a_number" Rate → skipped; USD and CNY are kept
        assert len(rows) == 2
        ccys = {r.ccy for r in rows}
        assert "USD" in ccys
        assert "CNY" in ccys
        assert "EUR" not in ccys

    def test_parse_empty_json_array(self) -> None:
        """Empty JSON array returns an empty list without raising."""
        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        rows = adapter._parse_cbu_json("[]")
        assert rows == []

    def test_parse_rate_is_decimal(self) -> None:
        """Parsed rates are Decimal (never float) to preserve money precision (T-02-15)."""
        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        rows = adapter._parse_cbu_json(CBU_SAMPLE)

        for row in rows:
            assert isinstance(row.rate, decimal.Decimal), (
                f"Rate for {row.ccy} must be Decimal, got {type(row.rate)}"
            )

    def test_parse_ccu_3_chars(self) -> None:
        """Parsed ccy values are exactly 3 characters."""
        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        rows = adapter._parse_cbu_json(CBU_SAMPLE)

        for row in rows:
            assert len(row.ccy) == 3, f"ccy must be 3 chars, got {row.ccy!r}"


# ── Adapter registration ────────────────────────────────────────────────────────

class TestCbuAdapterRegistration:
    """CbuRatesAdapter registers under 'cbu_rates' in the adapter registry."""

    def test_get_adapter_cbu_rates(self) -> None:
        """get_adapter('cbu_rates') returns the CbuRatesAdapter instance."""
        # Importing the adapter package triggers registration
        import app.ingest.cbu_rates.adapter  # noqa: F401, PLC0415
        from app.ingest.registry import get_adapter  # noqa: PLC0415

        adapter = get_adapter("cbu_rates")
        assert adapter is not None
        assert adapter.type_name == "cbu_rates"

    def test_adapter_satisfies_protocol(self) -> None:
        """CbuRatesAdapter satisfies the SourceAdapter Protocol at runtime."""
        import app.ingest.cbu_rates.adapter  # noqa: F401, PLC0415
        from app.ingest.base import SourceAdapter  # noqa: PLC0415
        from app.ingest.registry import get_adapter  # noqa: PLC0415

        adapter = get_adapter("cbu_rates")
        assert isinstance(adapter, SourceAdapter)

    def test_adapter_has_config_schema(self) -> None:
        """CbuRatesAdapter.config_schema is a pydantic BaseModel subclass."""
        from pydantic import BaseModel  # noqa: PLC0415

        from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

        adapter = CbuRatesAdapter()
        assert issubclass(adapter.config_schema, BaseModel)

    def test_task_module_registered(self) -> None:
        """fetch_cbu_rates task is registered in the Celery app after importing ingest_cbu."""
        import app.tasks.ingest_cbu  # noqa: F401, PLC0415
        from app.tasks.celery_app import celery_app  # noqa: PLC0415

        # The task must be registered under the exact name 'fetch_cbu_rates'
        task = celery_app.tasks.get("fetch_cbu_rates")
        assert task is not None, "fetch_cbu_rates task must be registered in Celery"


# ── DB-backed tests ────────────────────────────────────────────────────────────

@_requires_real_db
class TestUpsertFxRatesDB:
    """upsert_fx_rates idempotency and fetch_cbu_rates integration (live DB)."""

    @pytest.fixture(scope="class")
    def engine(self):
        import sqlalchemy as sa  # noqa: PLC0415
        return sa.create_engine(_DB_URL, pool_pre_ping=True)

    @pytest.fixture(scope="class")
    def migrated_db(self, engine):
        """Apply migrations before the class tests."""
        from alembic.config import Config  # noqa: PLC0415

        from alembic import command as alembic_command  # noqa: PLC0415

        backend_dir = Path(__file__).parent.parent
        alembic_cfg = Config(str(backend_dir / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
        alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")
        alembic_command.upgrade(alembic_cfg, "head")

        yield engine

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")

    def test_upsert_inserts_new_rows(self, migrated_db) -> None:
        """upsert_fx_rates inserts new rates into fx_rates."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.domains.pricing.fx import upsert_fx_rates  # noqa: PLC0415
        from app.ingest.cbu_rates.adapter import CbuRateRow  # noqa: PLC0415

        rate_date = datetime.date(2024, 3, 1)
        rates = [
            CbuRateRow(rate_date=rate_date, ccy="USD", rate=decimal.Decimal("12800.00")),
            CbuRateRow(rate_date=rate_date, ccy="CNY", rate=decimal.Decimal("1770.00")),
        ]

        with Session(migrated_db) as session:
            # Clean up any prior runs
            session.execute(
                sa.text("DELETE FROM fx_rates WHERE rate_date = :d"),
                {"d": rate_date},
            )
            session.commit()

        with Session(migrated_db) as session:
            inserted = upsert_fx_rates(session, rates)
            session.commit()

        assert inserted == 2

    def test_upsert_is_idempotent(self, migrated_db) -> None:
        """Second upsert for same date/ccy inserts 0 net rows (ON CONFLICT idempotent)."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.domains.pricing.fx import upsert_fx_rates  # noqa: PLC0415
        from app.ingest.cbu_rates.adapter import CbuRateRow  # noqa: PLC0415

        rate_date = datetime.date(2024, 3, 2)
        rates = [
            CbuRateRow(rate_date=rate_date, ccy="USD", rate=decimal.Decimal("12750.00")),
        ]

        with Session(migrated_db) as session:
            session.execute(
                sa.text("DELETE FROM fx_rates WHERE rate_date = :d"),
                {"d": rate_date},
            )
            session.commit()

        # First insert
        with Session(migrated_db) as session:
            upsert_fx_rates(session, rates)
            session.commit()

        # Verify count
        with Session(migrated_db) as session:
            count_before = session.execute(
                sa.text("SELECT COUNT(*) FROM fx_rates WHERE rate_date = :d AND ccy = 'USD'"),
                {"d": rate_date},
            ).scalar()
        assert count_before == 1

        # Same-day upsert: ON CONFLICT DO UPDATE — still 1 row (idempotent)
        updated_rates = [
            CbuRateRow(rate_date=rate_date, ccy="USD", rate=decimal.Decimal("12750.00")),
        ]
        with Session(migrated_db) as session:
            upsert_fx_rates(session, updated_rates)
            session.commit()

        with Session(migrated_db) as session:
            count_after = session.execute(
                sa.text("SELECT COUNT(*) FROM fx_rates WHERE rate_date = :d AND ccy = 'USD'"),
                {"d": rate_date},
            ).scalar()

        assert count_after == 1, (
            f"Second upsert must leave 1 row (idempotent), got {count_after}"
        )


def test_parse_cbu_json_real_ddmmyyyy_format() -> None:
    """Regression: the live CBU API returns DD.MM.YYYY dates (not ISO). Every row was
    being skipped as 'malformed date' → fx_rates stayed empty. Must now parse."""
    import datetime as _dt  # noqa: PLC0415
    import decimal as _dec  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

    body = _json.dumps([
        {"Ccy": "USD", "Rate": "11960.09", "Date": "21.07.2026"},
        {"Ccy": "EUR", "Rate": "13670.38", "Date": "21.07.2026"},
        {"Ccy": "RUB", "Rate": "152.53", "Date": "21.07.2026"},
    ])
    rows = CbuRatesAdapter()._parse_cbu_json(body)
    assert len(rows) == 3, "DD.MM.YYYY dates must parse (were being dropped)"
    assert rows[0].rate_date == _dt.date(2026, 7, 21)
    assert rows[0].ccy == "USD" and rows[0].rate == _dec.Decimal("11960.09")
