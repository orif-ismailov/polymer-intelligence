"""
Integration tests for the reference seed scripts.

Tests run against a live PostgreSQL 16 database (same conditions as
test_migration.py). Skipped when DATABASE_URL does not point to a real test DB.

The tests verify:
- Products are inserted on first run (PP, HDPE, LDPE, LLDPE, PVC, PET present)
- Product grades (UZ-producer) are inserted
- Running seed a second time inserts 0 additional rows (idempotent)
- synonyms.json is valid JSON and non-empty

Run locally with a migrated test DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_seed.py -v
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command as alembic_command

BACKEND_DIR = Path(__file__).parent.parent
SEED_DATA_DIR = BACKEND_DIR / "app" / "seed" / "data"

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

# Only integration-only test classes apply the skip; data-file tests and
# in-memory synonym tests always run (no DB required).
_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Seed integration tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine():
    """SQLAlchemy engine connected to the test database."""
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def migrated_db(engine):
    """Apply migrations before seed tests and clean up after."""
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    # Ensure clean state
    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")
    alembic_command.upgrade(alembic_cfg, "head")

    yield engine

    # Tear down
    alembic_command.downgrade(alembic_cfg, "base")


class TestSeedDataFiles:
    """Verify the seed JSON data files are valid and non-empty."""

    def test_products_json_is_valid(self) -> None:
        """products.json is valid JSON with at least 6 polymer products."""
        with open(SEED_DATA_DIR / "products.json") as f:
            products = json.load(f)
        assert isinstance(products, list), "products.json must be a JSON array"
        codes = {p["code"] for p in products}
        required = {"PP", "HDPE", "LDPE", "LLDPE", "PVC", "PET"}
        assert required.issubset(codes), (
            f"Missing required product codes: {required - codes}"
        )

    def test_grades_json_is_valid(self) -> None:
        """grades.json is valid JSON with UZ-producer grades."""
        with open(SEED_DATA_DIR / "grades.json") as f:
            grades = json.load(f)
        assert isinstance(grades, list), "grades.json must be a JSON array"
        assert len(grades) > 0, "grades.json must not be empty"
        # Must have grades for PP and HDPE at minimum
        product_codes = {g["product_code"] for g in grades}
        assert "PP" in product_codes, "grades.json must contain PP grades"
        assert "HDPE" in product_codes, "grades.json must contain HDPE grades"

    def test_synonyms_json_is_valid_and_non_empty(self) -> None:
        """synonyms.json is valid JSON and non-empty."""
        with open(SEED_DATA_DIR / "synonyms.json") as f:
            data = json.load(f)
        assert isinstance(data, dict), "synonyms.json must be a JSON object"
        # Remove comment keys
        synonyms = {k: v for k, v in data.items() if not k.startswith("_")}
        assert len(synonyms) > 0, "synonyms.json must contain product entries"
        # PP must have synonyms including Cyrillic
        assert "PP" in synonyms, "synonyms.json must contain PP entry"
        pp_syns = synonyms["PP"]
        assert any("полипропилен" in s.lower() for s in pp_syns), (
            "PP synonyms must include 'полипропилен'"
        )

    def test_synonyms_json_covers_all_products(self) -> None:
        """synonyms.json covers all product codes from products.json."""
        with open(SEED_DATA_DIR / "products.json") as f:
            products = json.load(f)
        with open(SEED_DATA_DIR / "synonyms.json") as f:
            data = json.load(f)
        synonyms = {k for k in data if not k.startswith("_")}
        product_codes = {p["code"] for p in products}
        assert product_codes.issubset(synonyms), (
            f"synonyms.json missing entries for: {product_codes - synonyms}"
        )


@_requires_real_db
class TestSeedProducts:
    """Integration tests for product seeding against a live DB."""

    def test_seed_products_inserts_expected_rows(self, migrated_db) -> None:
        """First seed run inserts the polymer products."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_products  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_db)
        with session_factory() as session:
            inserted = seed_products(session)
            session.commit()

        assert inserted >= 6, f"Expected at least 6 products inserted, got {inserted}"

    def test_seed_products_is_idempotent(self, migrated_db) -> None:
        """Second seed run inserts 0 additional rows."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_products  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_db)
        # First run (may already be seeded from previous test)
        with session_factory() as session:
            seed_products(session)
            session.commit()
        # Second run must insert 0
        with session_factory() as session:
            inserted = seed_products(session)
            session.commit()

        assert inserted == 0, f"Idempotent run must insert 0 rows, got {inserted}"

    def test_seed_products_required_codes_present(self, migrated_db) -> None:
        """After seeding, required product codes exist in the DB."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_all  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_db)
        with session_factory() as session:
            seed_all(session)

        with migrated_db.connect() as conn:
            result = conn.execute(
                sa.text("SELECT code FROM products ORDER BY code")
            )
            codes = {row[0] for row in result.fetchall()}

        required = {"PP", "HDPE", "LDPE", "LLDPE", "PVC", "PET"}
        assert required.issubset(codes), (
            f"Missing required product codes: {required - codes}"
        )


@_requires_real_db
class TestSeedGrades:
    """Integration tests for grade seeding against a live DB."""

    def test_seed_grades_inserts_rows(self, migrated_db) -> None:
        """First seed run inserts UZ-producer grades."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_all  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_db)
        with session_factory() as session:
            counts = seed_all(session)

        assert counts["grades"] >= 0  # May be 0 if already seeded

        # Verify grades exist
        with migrated_db.connect() as conn:
            result = conn.execute(
                sa.text("SELECT COUNT(*) FROM product_grades")
            )
            count = result.scalar()
        assert count > 0, "product_grades must have at least one row after seeding"

    def test_seed_grades_idempotent(self, migrated_db) -> None:
        """Running seed_all twice inserts 0 additional grade rows on second run."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_grades  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_db)
        # First run (idempotency baseline)
        with session_factory() as session:
            seed_grades(session)
            session.commit()
        # Second run
        with session_factory() as session:
            inserted = seed_grades(session)
            session.commit()

        assert inserted == 0, f"Idempotent grade seed must insert 0 rows, got {inserted}"


class TestSeedSynonyms:
    """Tests for synonyms loading (no DB write in Phase 1)."""

    def test_load_synonyms_returns_dict(self) -> None:
        """load_synonyms() returns a non-empty dict."""
        from app.seed.seed_reference import load_synonyms  # noqa: PLC0415

        synonyms = load_synonyms()
        assert isinstance(synonyms, dict), "load_synonyms() must return a dict"
        assert len(synonyms) > 0, "Synonyms dict must not be empty"

    def test_load_synonyms_pp_has_cyrillic_entry(self) -> None:
        """PP synonyms include a Cyrillic variant ('полипропилен')."""
        from app.seed.seed_reference import load_synonyms  # noqa: PLC0415

        synonyms = load_synonyms()
        assert "PP" in synonyms
        assert any("полипропилен" in s.lower() for s in synonyms["PP"])

    def test_load_synonyms_hdpe_has_cyrillic_abbreviation(self) -> None:
        """HDPE synonyms include 'ПЭВП' or 'ПЭВД' (Cyrillic abbreviation)."""
        from app.seed.seed_reference import load_synonyms  # noqa: PLC0415

        synonyms = load_synonyms()
        assert "HDPE" in synonyms
        hdpe = synonyms["HDPE"]
        assert any(s in ("ПЭВП", "ПЭВД", "ПЕНД") for s in hdpe), (
            f"HDPE synonyms missing Cyrillic abbreviation: {hdpe}"
        )
