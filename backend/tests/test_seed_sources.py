"""
Tests for the source seed script.

Verifies:
- The sources_seed.json data file is valid and has the expected 8 rows
- All seeded sources have is_enabled=false + last_test_ok_at NULL (invariant T-02-24)
- seed_sources is idempotent (second run inserts 0 additional rows)
- Data file has the expected adapter names (uzex_offers, uzex_contracts,
  uzex_deals, xarid_tenders, cbu_rates, and rss for the news sources)

Live-DB tests use the standard guard (DATABASE_URL with test_polymer).
Data-file and unit tests always run (no DB required).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
SOURCES_FILE = BACKEND_DIR / "app" / "seed" / "data" / "sources_seed.json"

# ── Live-DB skip guard ────────────────────────────────────────────────────────
_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Seed sources DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


# ── Data-file unit tests (always run, no DB) ─────────────────────────────────

class TestSourcesSeedDataFile:
    """Validates sources_seed.json without touching the database."""

    def test_file_exists(self) -> None:
        """sources_seed.json must exist."""
        assert SOURCES_FILE.exists(), f"Missing seed file: {SOURCES_FILE}"

    def test_file_is_valid_json(self) -> None:
        """sources_seed.json must be parseable JSON."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        assert isinstance(data, list), "sources_seed.json must be a JSON array"

    def test_has_expected_source_count(self) -> None:
        """sources_seed.json must contain exactly 8 source rows (5 markets + 3 news)."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        assert len(data) == 8, (
            f"Expected 8 source rows, got {len(data)}: "
            f"{[s.get('adapter') for s in data]}"
        )

    def test_expected_adapters_present(self) -> None:
        """All expected adapters must be present (news sources use the rss adapter)."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        adapters = {s["adapter"] for s in data}
        expected = {"uzex_offers", "uzex_contracts", "uzex_deals", "xarid_tenders", "cbu_rates", "rss"}
        assert adapters == expected, (
            f"Adapter mismatch — expected {expected}, got {adapters}"
        )

    def test_news_sources_are_flagged(self) -> None:
        """Every rss source is a news source (config.content_kind='news' + config.url)."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        news = [s for s in data if s["adapter"] == "rss"]
        assert len(news) == 3, f"Expected 3 news (rss) sources, got {len(news)}"
        for src in news:
            config = src.get("config", {})
            assert config.get("content_kind") == "news", (
                f"News source '{src['name']}' must set config.content_kind='news'"
            )
            assert config.get("url"), f"News source '{src['name']}' must have config.url"

    def test_all_sources_disabled_by_default(self) -> None:
        """All seeded sources must have is_enabled=false (T-02-24 invariant)."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        for src in data:
            assert src.get("is_enabled") is False, (
                f"Source '{src.get('adapter')}' has is_enabled={src.get('is_enabled')!r}, "
                f"must be false (T-02-24: no enable without a passing test)"
            )

    def test_all_sources_last_test_ok_at_null(self) -> None:
        """All seeded sources must have last_test_ok_at=null (T-02-24 invariant)."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        for src in data:
            assert src.get("last_test_ok_at") is None, (
                f"Source '{src.get('adapter')}' has last_test_ok_at={src.get('last_test_ok_at')!r}, "
                f"must be null (T-02-24: no enable without a passing test)"
            )

    def test_uzex_sources_have_config_with_urls(self) -> None:
        """UZEX adapter sources must have a config with a non-empty urls list."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        uzex_sources = [s for s in data if s["adapter"].startswith("uzex_")]
        for src in uzex_sources:
            config = src.get("config", {})
            urls = config.get("urls", [])
            assert isinstance(urls, list) and len(urls) > 0, (
                f"Source '{src['adapter']}' must have config.urls with at least one URL, "
                f"got: {urls!r}"
            )

    def test_uzex_sources_have_table_selector(self) -> None:
        """UZEX adapter sources must have config.table_selector."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        uzex_sources = [s for s in data if s["adapter"].startswith("uzex_")]
        for src in uzex_sources:
            config = src.get("config", {})
            assert "table_selector" in config, (
                f"Source '{src['adapter']}' must have config.table_selector"
            )

    def test_uzex_sources_have_columns(self) -> None:
        """UZEX adapter sources must have config.columns list."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        uzex_sources = [s for s in data if s["adapter"].startswith("uzex_")]
        for src in uzex_sources:
            config = src.get("config", {})
            columns = config.get("columns", [])
            assert isinstance(columns, list) and len(columns) > 0, (
                f"Source '{src['adapter']}' must have config.columns"
            )

    def test_cbu_rates_has_endpoint_in_config(self) -> None:
        """cbu_rates source must have config.endpoint."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        cbu = next(s for s in data if s["adapter"] == "cbu_rates")
        assert "endpoint" in cbu.get("config", {}), (
            "cbu_rates source must have config.endpoint"
        )

    def test_uzex_sources_country_is_uz(self) -> None:
        """UZEX sources must have country='UZ'."""
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        for src in data:
            if src["adapter"].startswith("uzex_"):
                assert src.get("country") == "UZ", (
                    f"Source '{src['adapter']}' must have country='UZ', "
                    f"got {src.get('country')!r}"
                )


# ── Unit tests: seed_sources function (mock session) ─────────────────────────

class TestSeedSourcesUnit:
    """seed_sources function: unit tests with a mock session."""

    def _make_mock_session(self, rowcount_first: int = 8) -> MagicMock:
        """Build a mock Session that simulates inserts (8 seeded sources)."""
        session = MagicMock()
        # Each execute() returns a mock result with rowcount
        results = []
        for i in range(8):
            r = MagicMock()
            r.rowcount = 1 if i < rowcount_first else 0
            results.append(r)
        session.execute.side_effect = results
        return session

    def test_seed_sources_returns_count(self) -> None:
        """seed_sources returns the number of rows inserted."""
        from app.seed.seed_sources import seed_sources  # noqa: PLC0415

        session = self._make_mock_session(rowcount_first=8)
        count = seed_sources(session)
        assert count == 8, f"Expected 8 inserted, got {count}"
        session.flush.assert_called_once()

    def test_seed_sources_idempotent_second_run_inserts_zero(self) -> None:
        """seed_sources second run inserts 0 rows (idempotency)."""
        from app.seed.seed_sources import seed_sources  # noqa: PLC0415

        # Simulate second run: all rowcounts = 0 (rows already exist)
        session = MagicMock()
        zero_result = MagicMock()
        zero_result.rowcount = 0
        session.execute.return_value = zero_result

        count = seed_sources(session)
        assert count == 0, (
            f"Second run of seed_sources must insert 0 rows, got {count}"
        )

    def test_seed_sources_uses_is_enabled_false(self) -> None:
        """seed_sources SQL must hard-code is_enabled=false (T-02-24)."""
        import inspect  # noqa: PLC0415

        from app.seed import seed_sources as seed_module  # noqa: PLC0415

        source = inspect.getsource(seed_module)
        assert "false" in source.lower(), (
            "seed_sources SQL must set is_enabled=false"
        )
        # Ensure it never sets is_enabled=true
        assert "is_enabled = true" not in source and "is_enabled=true" not in source, (
            "seed_sources must never set is_enabled=true"
        )

    def test_seed_sources_uses_last_test_ok_at_null(self) -> None:
        """seed_sources SQL must hard-code last_test_ok_at=NULL (T-02-24)."""
        import inspect  # noqa: PLC0415

        from app.seed import seed_sources as seed_module  # noqa: PLC0415

        source = inspect.getsource(seed_module)
        assert "null" in source.lower(), (
            "seed_sources SQL must set last_test_ok_at=NULL"
        )

    def test_seed_sources_executes_one_insert_per_source(self) -> None:
        """seed_sources executes exactly one INSERT statement per source row (8)."""
        from app.seed.seed_sources import seed_sources  # noqa: PLC0415

        session = MagicMock()
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result

        seed_sources(session)
        # Should be called once per source (8 sources in the seed file)
        assert session.execute.call_count == 8, (
            f"Expected 8 execute() calls, got {session.execute.call_count}"
        )


# ── Live-DB integration tests ─────────────────────────────────────────────────

@_requires_real_db
class TestSeedSourcesIntegrationDB:
    """Integration tests for seed_sources with a live PostgreSQL database."""

    @pytest.fixture(scope="class")
    def engine(self):
        import sqlalchemy as sa  # noqa: PLC0415
        return sa.create_engine(_DB_URL, pool_pre_ping=True)

    @pytest.fixture(scope="class")
    def migrated_db(self, engine):
        """Apply migrations before seed tests and clean up after."""
        import contextlib  # noqa: PLC0415

        from alembic.config import Config  # noqa: PLC0415

        from alembic import command as alembic_command  # noqa: PLC0415

        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")
        alembic_command.upgrade(alembic_cfg, "head")

        yield engine

        with contextlib.suppress(Exception):
            alembic_command.downgrade(alembic_cfg, "base")

    def test_seed_sources_inserts_all_rows(self, migrated_db) -> None:
        """seed_sources inserts all 8 source rows on a fresh DB."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_sources import seed_sources  # noqa: PLC0415

        SessionLocal = sessionmaker(bind=migrated_db)  # noqa: N806
        with SessionLocal() as session:
            count = seed_sources(session)
            session.commit()

        assert count == 8, f"Expected 8 inserted, got {count}"

        # Verify rows are in DB
        with sa.engine.connect(migrated_db) as conn:
            n = conn.execute(
                sa.text("SELECT COUNT(*) FROM sources")
            ).scalar()
        assert n == 8, f"Expected 8 rows in sources, got {n}"

    def test_seed_sources_idempotent_in_db(self, migrated_db) -> None:
        """seed_sources second run inserts 0 additional rows in a live DB."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_sources import seed_sources  # noqa: PLC0415

        SessionLocal = sessionmaker(bind=migrated_db)  # noqa: N806

        # First run already done in test_seed_sources_inserts_four_rows
        with SessionLocal() as session:
            count = seed_sources(session)
            session.commit()

        assert count == 0, (
            f"Second run of seed_sources must insert 0 rows, got {count}"
        )

    def test_seeded_sources_all_disabled(self, migrated_db) -> None:
        """All seeded sources have is_enabled=false (invariant T-02-24)."""
        import sqlalchemy as sa  # noqa: PLC0415

        with sa.engine.connect(migrated_db) as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT adapter, name, is_enabled, last_test_ok_at "
                    "FROM sources WHERE adapter IN "
                    "('uzex_offers','uzex_contracts','uzex_deals','xarid_tenders','cbu_rates','rss')"
                )
            ).fetchall()

        assert len(rows) == 8, f"Expected 8 seeded sources, got {len(rows)}"
        for row in rows:
            adapter, name, is_enabled, last_test_ok_at = row
            assert is_enabled is False, (
                f"Source '{adapter}/{name}' has is_enabled={is_enabled!r}, "
                "must be false (T-02-24: no enable without a passing test)"
            )
            assert last_test_ok_at is None, (
                f"Source '{adapter}/{name}' has last_test_ok_at={last_test_ok_at!r}, "
                "must be NULL (T-02-24 invariant)"
            )
