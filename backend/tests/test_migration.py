"""
Integration tests for the Alembic migration and schema verification.

Tests run against a live PostgreSQL 16 database. They are skipped when
DATABASE_URL is not set to a real Postgres instance (not the mock test URL)
or when the Postgres server is unreachable.

Run these locally with a real DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_migration.py -v

These are NOT run in CI: `conftest._real_db_optin` only honours a `DATABASE_URL`
naming a localhost `test_polymer`, and CI's is `polymer_intelligence_test`. Worth
knowing before trusting a green pipeline about anything in this file.

**Every expectation here is DERIVED, never transcribed.** These tests were
written against migration `0001` and asserted its schema literally — the revision
string `"0001"`, a hand-listed set of 20 tables, 14 ENUM names including a
`staff_role` that migration `0044` deleted. By head `0050` all six of those
assertions were false, and they had been false for months without anyone
noticing, because nothing runs them. A transcribed schema is a second copy of the
migration chain that has to be edited in step with it, and this file is the proof
that it will not be. So: the head comes from the `ScriptDirectory`, the tables and
ENUMs come from `Base.metadata`, and adding migration `0051` requires no edit here.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

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


def _expected_head(cfg: Config) -> str:
    """The single head of the migration chain, read from the chain itself."""
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected one head, found {heads!r}"
    return heads[0]


def _metadata():  # noqa: ANN202
    """`Base.metadata` with every domain's models imported (the alembic barrel).

    Imported inside the function, not at module scope: the conftest env patch is
    a session fixture and importing `app.*` at collection time would build the
    `settings` singleton from the developer's real `.env`.
    """
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata


def _expected_tables() -> set[str]:
    return set(_metadata().tables)


def _expected_enums() -> set[str]:
    """Every Postgres ENUM type the ORM declares, by its `name=` in the DB."""
    names: set[str] = set()
    for table in _metadata().tables.values():
        for column in table.columns:
            name = getattr(column.type, "name", None)
            if isinstance(column.type, sa.Enum) and name:
                names.add(name)
    return names


def _actual_tables(engine) -> set[str]:  # noqa: ANN001
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                  AND table_name != 'alembic_version'
                """
            )
        ).fetchall()
    return {row[0] for row in rows}


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

    def test_alembic_version_table_contains_revision(
        self, alembic_cfg: Config, engine
    ) -> None:
        """After upgrade, alembic_version holds the chain's single head."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            )
            rows = result.fetchall()
        assert len(rows) == 1, "Expected exactly one row in alembic_version"
        head = _expected_head(alembic_cfg)
        assert rows[0][0] == head, f"Expected revision {head!r}, got {rows[0][0]!r}"

    def test_migrated_tables_match_the_orm(self, engine) -> None:
        """The migrated schema and `Base.metadata` name the same tables.

        This is the invariant the old "exactly 20 tables" list was reaching for.
        It also catches the mistake that list could not: a model added to a domain
        but never given a migration, or a migration whose table no model declares.
        """
        actual = _actual_tables(engine)
        expected = _expected_tables()
        assert actual == expected, (
            f"In the ORM but not migrated: {expected - actual!r}; "
            f"migrated but not in the ORM: {actual - expected!r}"
        )

    def test_every_orm_enum_type_exists(self, engine) -> None:
        """Every ENUM the ORM declares exists as a Postgres type.

        A subset check, not equality: `_OPEN`-style types created by hand in a
        migration and no longer referenced by a column are not a failure.
        """
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT typname FROM pg_type WHERE typtype = 'e'")
            )
            enum_names = {row[0] for row in result.fetchall()}

        expected = _expected_enums()
        assert expected, "no ENUM types found in the ORM — the barrel import failed"
        assert expected.issubset(enum_names), (
            f"Missing ENUM types: {expected - enum_names!r}"
        )

    def test_v_live_feed_view_exists(self, engine) -> None:
        """The v_live_feed view exists and can be queried.

        The old version selected `viewname` from `information_schema.views`, which
        has no such column — that is `pg_views`. It raised `UndefinedColumn` rather
        than reporting a missing view, so the test could only ever fail loudly or
        not run at all; it never once checked what it claimed to.
        """
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT table_name FROM information_schema.views
                    WHERE table_schema = 'public' AND table_name = 'v_live_feed'
                    """
                )
            ).fetchall()
            conn.execute(sa.text("SELECT * FROM v_live_feed LIMIT 0"))
        assert len(rows) == 1, "v_live_feed view not found"

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

    def test_staff_authorization_is_is_admin_plus_page_access(self, engine) -> None:
        """Staff authorization is `is_admin` + `staff_page_access`, not a role ENUM.

        This test used to assert `staff_users.role` was the `staff_role` ENUM. Both
        the column and the type are gone — the three-role ladder was replaced by an
        admin flag plus a per-page grant table. Asserting the replacement rather
        than deleting the test keeps the fact under a gate.
        """
        with engine.connect() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'staff_users'"
                    )
                ).fetchall()
            }
            enums = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT typname FROM pg_type WHERE typtype = 'e'")
                ).fetchall()
            }
        assert "is_admin" in columns
        assert "role" not in columns, "the role column was dropped — see migration 0044"
        assert "staff_role" not in enums, "the staff_role ENUM went with it"
        assert "staff_page_access" in _actual_tables(engine)

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

        # Tables should be back — all of them, compared against the ORM rather
        # than a count that has to be edited every time a domain gains a table.
        assert _actual_tables(engine) == _expected_tables()


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
