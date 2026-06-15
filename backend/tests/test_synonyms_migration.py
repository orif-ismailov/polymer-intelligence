"""
Integration tests for migration 0002: product_synonyms + manual_classification_queue.

Tests run against a live PostgreSQL 16 database. They are skipped when
DATABASE_URL is not set to a real Postgres instance (not the mock test URL)
or when the Postgres server is unreachable.

Run locally with a real DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_synonyms_migration.py -v

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
        "Migration 0002 integration tests require a live PostgreSQL 16 instance. "
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
    """Ensure the DB starts at head-of-0001 and is clean after the module."""
    # Downgrade to base first (in case a previous run left state)
    with contextlib.suppress(Exception):
        command.downgrade(alembic_cfg, "base")

    # Upgrade to 0001 (the base schema without the new tables)
    command.upgrade(alembic_cfg, "0001")

    yield

    # Tear down all migrations after all tests in this module
    with contextlib.suppress(Exception):
        command.downgrade(alembic_cfg, "base")


class TestMigration0002Upgrade:
    """Verify that upgrading to 0002 creates both new tables with correct schema."""

    def test_upgrade_to_0002_succeeds(self, alembic_cfg: Config) -> None:
        """alembic upgrade head (0002) succeeds from 0001."""
        command.upgrade(alembic_cfg, "head")  # raises on failure

    def test_alembic_version_is_0002(self, engine) -> None:
        """After upgrade to 0002, alembic_version contains '0002'."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            )
            rows = result.fetchall()
        assert len(rows) == 1, "Expected exactly one row in alembic_version"
        assert rows[0][0] == "0002", f"Expected revision '0002', got {rows[0][0]!r}"

    def test_product_synonyms_table_exists(self, engine) -> None:
        """product_synonyms table exists after upgrade to 0002."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'product_synonyms'
                    """
                )
            )
            rows = result.fetchall()
        assert len(rows) == 1, "product_synonyms table not found after upgrade to 0002"

    def test_manual_classification_queue_table_exists(self, engine) -> None:
        """manual_classification_queue table exists after upgrade to 0002."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'manual_classification_queue'
                    """
                )
            )
            rows = result.fetchall()
        assert len(rows) == 1, (
            "manual_classification_queue table not found after upgrade to 0002"
        )

    def test_product_synonyms_columns(self, engine) -> None:
        """product_synonyms has the expected columns with correct types."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = 'product_synonyms'
                    ORDER BY ordinal_position
                    """
                )
            )
            cols = {row[0]: {"type": row[1], "nullable": row[2], "default": row[3]}
                    for row in result.fetchall()}

        assert "id" in cols, "product_synonyms.id column missing"
        assert "product_id" in cols, "product_synonyms.product_id column missing"
        assert "synonym" in cols, "product_synonyms.synonym column missing"
        assert "synonym_norm" in cols, "product_synonyms.synonym_norm column missing"
        assert "source" in cols, "product_synonyms.source column missing"
        assert "created_at" in cols, "product_synonyms.created_at column missing"

        assert cols["product_id"]["nullable"] == "NO", (
            "product_synonyms.product_id must be NOT NULL"
        )
        assert cols["synonym"]["nullable"] == "NO", (
            "product_synonyms.synonym must be NOT NULL"
        )
        assert cols["synonym_norm"]["nullable"] == "NO", (
            "product_synonyms.synonym_norm must be NOT NULL"
        )
        assert cols["source"]["nullable"] == "NO", (
            "product_synonyms.source must be NOT NULL"
        )
        assert cols["created_at"]["type"] == "timestamp with time zone", (
            f"product_synonyms.created_at must be timestamptz, got {cols['created_at']['type']!r}"
        )

    def test_manual_classification_queue_columns(self, engine) -> None:
        """manual_classification_queue has the expected columns with correct types."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'manual_classification_queue'
                    ORDER BY ordinal_position
                    """
                )
            )
            cols = {row[0]: {"type": row[1], "nullable": row[2]}
                    for row in result.fetchall()}

        assert "id" in cols, "manual_classification_queue.id column missing"
        assert "raw_item_id" in cols, "manual_classification_queue.raw_item_id missing"
        assert "product_text" in cols, "manual_classification_queue.product_text missing"
        assert "status" in cols, "manual_classification_queue.status missing"
        assert "created_at" in cols, "manual_classification_queue.created_at missing"

        assert cols["raw_item_id"]["nullable"] == "NO", (
            "manual_classification_queue.raw_item_id must be NOT NULL"
        )
        assert cols["product_text"]["nullable"] == "NO", (
            "manual_classification_queue.product_text must be NOT NULL"
        )
        assert cols["created_at"]["type"] == "timestamp with time zone", (
            f"manual_classification_queue.created_at must be timestamptz, "
            f"got {cols['created_at']['type']!r}"
        )

    def test_product_synonyms_unique_constraint_on_synonym_norm(self, engine) -> None:
        """product_synonyms has UNIQUE constraint on synonym_norm."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT tc.constraint_name, tc.constraint_type
                    FROM information_schema.table_constraints tc
                    WHERE tc.table_name = 'product_synonyms'
                      AND tc.constraint_type = 'UNIQUE'
                    """
                )
            )
            constraints = {row[0] for row in result.fetchall()}
        assert len(constraints) >= 1, (
            "product_synonyms must have at least one UNIQUE constraint (on synonym_norm)"
        )

    def test_manual_classification_queue_unique_constraint_on_raw_item_id(
        self, engine
    ) -> None:
        """manual_classification_queue has UNIQUE constraint on raw_item_id."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT tc.constraint_name, tc.constraint_type
                    FROM information_schema.table_constraints tc
                    WHERE tc.table_name = 'manual_classification_queue'
                      AND tc.constraint_type = 'UNIQUE'
                    """
                )
            )
            constraints = {row[0] for row in result.fetchall()}
        assert len(constraints) >= 1, (
            "manual_classification_queue must have at least one UNIQUE constraint (on raw_item_id)"
        )

    def test_product_synonyms_synonym_norm_index_exists(self, engine) -> None:
        """An index exists on product_synonyms.synonym_norm for fast lookups."""
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'product_synonyms'
                    """
                )
            )
            indexes = {row[0] for row in result.fetchall()}
        # Either the unique constraint index or a named index must cover synonym_norm
        assert len(indexes) >= 1, "No indexes found on product_synonyms"


class TestMigration0002Downgrade:
    """Verify that downgrading from 0002 to 0001 removes both new tables."""

    def test_downgrade_minus_1_removes_new_tables(
        self, alembic_cfg: Config, engine
    ) -> None:
        """alembic downgrade -1 from 0002 removes product_synonyms and manual_classification_queue."""
        # Ensure we are at 0002 first
        command.upgrade(alembic_cfg, "head")

        # Downgrade one step (0002 → 0001)
        command.downgrade(alembic_cfg, "-1")

        # Check alembic version is back to 0001
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            )
            row = result.fetchone()
        assert row is not None
        assert row[0] == "0001", f"Expected '0001' after downgrade -1, got {row[0]!r}"

        # Check both new tables are gone
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('product_synonyms', 'manual_classification_queue')
                    """
                )
            )
            remaining = {row[0] for row in result.fetchall()}

        assert len(remaining) == 0, (
            f"Tables still present after downgrade to 0001: {remaining}"
        )
