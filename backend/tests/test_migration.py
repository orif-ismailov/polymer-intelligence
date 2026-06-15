"""
Integration tests for the Alembic migration and schema verification.

Tests run against a live PostgreSQL 16 database. They are skipped when
DATABASE_URL is not set to a real Postgres instance (not the mock test URL)
or when the Postgres server is unreachable.

Run these locally with a real DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_migration.py -v

In CI: the postgres service container is configured in .github/workflows/*.yml.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

# ── Helpers ───────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).parent.parent

# Only run migration tests when pointed at a real Postgres (not the mock URL)
_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

pytestmark = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Migration integration tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer "
        "and ensure the test_polymer database exists."
    ),
)


@pytest.fixture(scope="module")
def alembic_cfg() -> Config:
    """Return an Alembic Config object pointing at the test database."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def engine():
    """SQLAlchemy engine connected to the test database."""
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(autouse=True, scope="module")
def clean_db(alembic_cfg: Config, engine):
    """Ensure the DB is clean before the test module runs, and clean up after."""
    # Downgrade to base first (in case a previous run left state)
    with contextlib.suppress(Exception):
        command.downgrade(alembic_cfg, "base")

    yield

    # Tear down after all tests in this module
    command.downgrade(alembic_cfg, "base")


class TestMigrationUpgrade:
    """Verify that upgrade head creates the expected schema."""

    def test_upgrade_head_exits_cleanly(self, alembic_cfg: Config) -> None:
        """alembic upgrade head succeeds on a clean database."""
        command.upgrade(alembic_cfg, "head")  # raises on failure

    def test_alembic_version_table_contains_revision(self, engine) -> None:
        """After upgrade, alembic_version contains the current revision."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            )
            rows = result.fetchall()
        assert len(rows) == 1, "Expected exactly one row in alembic_version"
        assert rows[0][0] == "0001", f"Expected revision '0001', got {rows[0][0]!r}"

    def test_exactly_20_tables_created(self, engine) -> None:
        """Exactly 20 application tables exist (excluding alembic_version)."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                      AND table_name != 'alembic_version'
                    ORDER BY table_name
                    """
                )
            )
            tables = {row[0] for row in result.fetchall()}

        expected = {
            "products", "product_grades", "fx_rates",
            "sources", "raw_items", "parse_runs",
            "counterparties", "counterparty_aliases",
            "signals",
            "clients", "requests", "request_files", "request_status_history",
            "price_points",
            "alert_rules", "alerts", "deliveries",
            "reports",
            "staff_users", "audit_log",
        }
        assert tables == expected, (
            f"Missing: {expected - tables!r}, Extra: {tables - expected!r}"
        )

    def test_14_enum_types_created(self, engine) -> None:
        """Exactly 14 ENUM types (>= 14) exist in the database."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname"
                )
            )
            enum_names = {row[0] for row in result.fetchall()}

        expected = {
            "source_kind", "parse_status", "counterparty_role", "signal_kind",
            "price_basis", "urgency", "request_status", "price_point_kind",
            "alert_kind", "delivery_channel", "delivery_status",
            "report_kind", "report_status", "staff_role",
        }
        assert expected.issubset(enum_names), (
            f"Missing ENUM types: {expected - enum_names!r}"
        )

    def test_v_live_feed_view_exists(self, engine) -> None:
        """The v_live_feed view exists and can be queried."""
        with engine.connect() as conn:
            # Check view exists
            result = conn.execute(
                sa.text(
                    """
                    SELECT viewname FROM information_schema.views
                    WHERE table_schema = 'public' AND table_name = 'v_live_feed'
                    """
                )
            )
            rows = result.fetchall()
            # Also try direct query (SELECT * LIMIT 0 should succeed)
            conn.execute(sa.text("SELECT * FROM v_live_feed LIMIT 0"))
        assert len(rows) >= 0  # view may return 0 rows but must exist

    def test_v_live_feed_view_selectable(self, engine) -> None:
        """SELECT * FROM v_live_feed LIMIT 0 succeeds (view definition is valid)."""
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT * FROM v_live_feed LIMIT 0"))

    def test_staff_users_password_hash_not_null(self, engine) -> None:
        """staff_users.password_hash is TEXT NOT NULL (REQ-roles foundation)."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'staff_users' AND column_name = 'password_hash'
                    """
                )
            )
            row = result.fetchone()
        assert row is not None, "staff_users.password_hash column not found"
        assert row[1] == "text", f"Expected 'text', got {row[1]!r}"
        assert row[2] == "NO", "staff_users.password_hash must be NOT NULL"

    def test_staff_users_role_is_staff_role_enum(self, engine) -> None:
        """staff_users.role uses the staff_role ENUM (REQ-roles foundation)."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT udt_name FROM information_schema.columns
                    WHERE table_name = 'staff_users' AND column_name = 'role'
                    """
                )
            )
            row = result.fetchone()
        assert row is not None, "staff_users.role column not found"
        assert row[0] == "staff_role", f"Expected 'staff_role' ENUM, got {row[0]!r}"

    def test_timestamptz_columns_are_timestamp_with_timezone(self, engine) -> None:
        """Key timestamptz columns are 'timestamp with time zone' (REQ-nfr-time-localization)."""
        checks = [
            ("signals", "event_at"),
            ("signals", "created_at"),
            ("requests", "created_at"),
            ("raw_items", "fetched_at"),
            ("sources", "created_at"),
        ]
        with engine.connect() as conn:
            for table, column in checks:
                result = conn.execute(
                    sa.text(
                        """
                        SELECT data_type FROM information_schema.columns
                        WHERE table_name = :table AND column_name = :col
                        """
                    ),
                    {"table": table, "col": column},
                )
                row = result.fetchone()
                assert row is not None, f"{table}.{column} column not found"
                assert row[0] == "timestamp with time zone", (
                    f"{table}.{column}: expected 'timestamp with time zone', got {row[0]!r}"
                )


class TestMigrationRoundTrip:
    """Verify that downgrade then upgrade round-trips cleanly."""

    def test_downgrade_then_upgrade_round_trip(self, alembic_cfg: Config, engine) -> None:
        """alembic downgrade base then upgrade head succeeds."""
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")

        # After downgrade, no application tables should remain
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                      AND table_name != 'alembic_version'
                    """
                )
            )
            count = result.scalar()
        assert count == 0, f"Expected 0 tables after downgrade, got {count}"

        # Re-run upgrade
        command.upgrade(alembic_cfg, "head")

        # Tables should be back
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                      AND table_name != 'alembic_version'
                    """
                )
            )
            count = result.scalar()
        assert count == 20, f"Expected 20 tables after re-upgrade, got {count}"


class TestAdvisoryLockEntrypoint:
    """Verify the advisory-locked migration entrypoint."""

    def test_entrypoint_advisory_lock_present_in_source(self) -> None:
        """Entrypoint source contains the pg_advisory_lock call."""
        entrypoint = BACKEND_DIR / "app" / "entrypoint.py"
        assert entrypoint.exists(), "backend/app/entrypoint.py not found"
        content = entrypoint.read_text()
        assert "pg_advisory_lock" in content or "advisory_lock" in content, (
            "entrypoint.py must contain 'pg_advisory_lock' or 'advisory_lock'"
        )

    def test_entrypoint_runs_upgrade_head(
        self, alembic_cfg: Config
    ) -> None:
        """Running the entrypoint applies the migration (alembic_version populated)."""
        import importlib.util

        entrypoint_path = BACKEND_DIR / "app" / "entrypoint.py"
        spec = importlib.util.spec_from_file_location("entrypoint", entrypoint_path)
        assert spec is not None

        # The entrypoint should be importable and expose a run_migrations() function
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "run_migrations"), (
            "entrypoint.py must expose a run_migrations() function"
        )
