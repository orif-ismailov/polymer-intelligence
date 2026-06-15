"""
Tests for the relevance service: normalize_term, match_product, queue_for_classification.

Most tests are unit tests (no DB required).
DB-backed tests use the live-DB skip guard from test_migration.py.

Run locally with a migrated, seeded test DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_relevance_service.py -v
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command as alembic_command

# ── Skip guard ────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Relevance service DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine():
    """SQLAlchemy engine connected to the test database."""
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def migrated_seeded_db(engine):
    """Apply migrations and seed products before relevance tests; clean up after."""
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    # Ensure clean state
    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")
    alembic_command.upgrade(alembic_cfg, "head")

    # Seed products so product_id lookups work
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from app.seed.seed_reference import seed_all  # noqa: PLC0415

    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        seed_all(session)

    yield engine

    # Tear down
    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")


# ── Unit tests for normalize_term ─────────────────────────────────────────────


class TestNormalizeTerm:
    """normalize_term() must be deterministic and case/space insensitive."""

    def test_lowercase(self) -> None:
        """normalize_term lowercases input."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        assert normalize_term("HDPE") == "hdpe"
        assert normalize_term("Полипропилен") == "полипропилен"

    def test_strips_leading_trailing_whitespace(self) -> None:
        """normalize_term strips surrounding whitespace."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        assert normalize_term("  пп  ") == "пп"
        assert normalize_term("\tPP\n") == "pp"

    def test_collapses_internal_whitespace(self) -> None:
        """normalize_term collapses internal whitespace runs to single spaces."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        assert normalize_term("полиэтилен  высокой   плотности") == (
            "полиэтилен высокой плотности"
        )

    def test_deterministic(self) -> None:
        """normalize_term returns the same output for the same input every call."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        term = "  ПолиПропилен  "
        result1 = normalize_term(term)
        result2 = normalize_term(term)
        assert result1 == result2

    def test_mixed_case_and_spaces(self) -> None:
        """Full round-trip: mixed case + extra spaces → normalized form."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        assert normalize_term("  ПолиПропилен ") == "полипропилен"

    def test_empty_string(self) -> None:
        """normalize_term handles empty string without raising."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        result = normalize_term("")
        assert result == ""

    def test_already_normalized(self) -> None:
        """normalize_term is idempotent — already-normalized strings are unchanged."""
        from app.services.relevance_service import normalize_term  # noqa: PLC0415

        term = "полипропилен"
        assert normalize_term(normalize_term(term)) == normalize_term(term)


# ── DB-backed tests ───────────────────────────────────────────────────────────


@_requires_real_db
class TestMatchProduct:
    """match_product() resolves polymer synonyms to product_id; unknown → None."""

    def test_match_product_pp_cyrillic(self, migrated_seeded_db) -> None:
        """match_product resolves 'полипропилен' to the PP product_id."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_synonyms  # noqa: PLC0415
        from app.services.relevance_service import match_product  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            seed_synonyms(session)
            session.commit()
            result = match_product(session, "полипропилен")

        assert result is not None, "'полипропилен' must resolve to PP product_id"

    def test_match_product_pp_mixed_case(self, migrated_seeded_db) -> None:
        """match_product is case-insensitive: 'ПолиПропилен' resolves to PP."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import match_product  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            result = match_product(session, "ПолиПропилен")

        assert result is not None, "'ПолиПропилен' must resolve to PP product_id"

    def test_match_product_pp_with_extra_spaces(self, migrated_seeded_db) -> None:
        """match_product trims spaces: '  полипропилен  ' resolves to PP."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import match_product  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            result = match_product(session, "  полипропилен  ")

        assert result is not None, "'  полипропилен  ' must resolve to PP product_id"

    def test_match_product_unknown_returns_none(self, migrated_seeded_db) -> None:
        """match_product returns None for unrecognized goods ('цемент')."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import match_product  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            result = match_product(session, "цемент")

        assert result is None, "'цемент' is not a polymer — must return None"

    def test_match_product_admin_topup(self, migrated_seeded_db) -> None:
        """Admin-added synonym row is picked up live — no code change needed (SC#4)."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import match_product, normalize_term  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        new_synonym = "тестовый_полимер_xyz"
        new_norm = normalize_term(new_synonym)

        with session_factory() as session:
            # Verify it doesn't resolve before admin-add
            result_before = match_product(session, new_synonym)
            assert result_before is None, "Novel synonym must not resolve before admin-add"

            # Get PP product_id
            row = session.execute(
                sa.text("SELECT id FROM products WHERE code = 'PP'")
            ).fetchone()
            assert row is not None, "PP product must exist in seeded DB"
            pp_product_id = row[0]

            # Admin inserts a new synonym directly (no code change)
            session.execute(
                sa.text(
                    """
                    INSERT INTO product_synonyms (product_id, synonym, synonym_norm, source)
                    VALUES (:product_id, :synonym, :norm, 'admin')
                    ON CONFLICT (synonym_norm) DO NOTHING
                    """
                ),
                {"product_id": pp_product_id, "synonym": new_synonym, "norm": new_norm},
            )
            session.commit()

            # Next call must pick it up without any code change
            result_after = match_product(session, new_synonym)

        assert result_after == pp_product_id, (
            f"Admin-added synonym must resolve to PP product_id {pp_product_id}, "
            f"got {result_after}"
        )


@_requires_real_db
class TestSeedSynonymsDB:
    """seed_synonyms() inserts synonyms idempotently into product_synonyms."""

    def test_seed_synonyms_inserts_rows(self, migrated_seeded_db) -> None:
        """First call to seed_synonyms inserts N rows (N > 0)."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_synonyms  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            # Clean up any prior seed from other tests
            session.execute(sa.text("DELETE FROM product_synonyms"))
            session.commit()

        with session_factory() as session:
            inserted = seed_synonyms(session)
            session.commit()

        assert inserted > 0, f"seed_synonyms must insert at least 1 row, got {inserted}"

    def test_seed_synonyms_is_idempotent(self, migrated_seeded_db) -> None:
        """Second call to seed_synonyms inserts 0 rows and does not raise."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_synonyms  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        # First run (may already have data from previous test)
        with session_factory() as session:
            seed_synonyms(session)
            session.commit()
        # Second run must insert 0
        with session_factory() as session:
            inserted = seed_synonyms(session)
            session.commit()

        assert inserted == 0, (
            f"Idempotent seed_synonyms must insert 0 rows on second run, got {inserted}"
        )

    def test_seed_synonyms_skips_comment_key(self, migrated_seeded_db) -> None:
        """seed_synonyms does not create rows for the '_comment' key in synonyms.json."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.seed.seed_reference import seed_synonyms  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)
        with session_factory() as session:
            seed_synonyms(session)
            session.commit()
            result = session.execute(
                sa.text("SELECT COUNT(*) FROM product_synonyms WHERE synonym ILIKE '%comment%'")
            ).scalar()

        assert result == 0, "_comment key must not create synonym rows"


@_requires_real_db
class TestQueueForClassification:
    """queue_for_classification() inserts into manual_classification_queue idempotently."""

    def test_queue_inserts_row(self, migrated_seeded_db) -> None:
        """queue_for_classification inserts one row into manual_classification_queue."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import queue_for_classification  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)

        # Insert a raw_item to FK-reference
        with session_factory() as session:
            # Create a source for the raw item
            source_row = session.execute(
                sa.text(
                    """
                    INSERT INTO sources (kind, adapter, name, url, is_enabled, consecutive_failures)
                    VALUES ('exchange', 'test_adapter', 'Test Source', NULL, false, 0)
                    RETURNING id
                    """
                )
            ).fetchone()
            source_id = source_row[0]

            raw_row = session.execute(
                sa.text(
                    """
                    INSERT INTO raw_items (source_id, content_hash, parse_status)
                    VALUES (:source_id, '\\x01'::bytea, 'pending')
                    RETURNING id
                    """
                ),
                {"source_id": source_id},
            ).fetchone()
            raw_item_id = raw_row[0]
            session.commit()

        with session_factory() as session:
            queue_for_classification(session, raw_item_id, "неизвестный товар")
            session.commit()

            count = session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM manual_classification_queue WHERE raw_item_id = :id"
                ),
                {"id": raw_item_id},
            ).scalar()

        assert count == 1, f"Expected 1 row in queue, got {count}"

    def test_queue_is_idempotent(self, migrated_seeded_db) -> None:
        """queue_for_classification with same raw_item_id inserts 0 on second call (ON CONFLICT)."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import queue_for_classification  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)

        # Insert a raw_item to FK-reference
        with session_factory() as session:
            source_row = session.execute(
                sa.text(
                    """
                    INSERT INTO sources (kind, adapter, name, url, is_enabled, consecutive_failures)
                    VALUES ('exchange', 'test_adapter2', 'Test Source 2', NULL, false, 0)
                    RETURNING id
                    """
                )
            ).fetchone()
            source_id = source_row[0]

            raw_row = session.execute(
                sa.text(
                    """
                    INSERT INTO raw_items (source_id, content_hash, parse_status)
                    VALUES (:source_id, '\\x02'::bytea, 'pending')
                    RETURNING id
                    """
                ),
                {"source_id": source_id},
            ).fetchone()
            raw_item_id = raw_row[0]
            session.commit()

        # First call
        with session_factory() as session:
            queue_for_classification(session, raw_item_id, "цемент")
            session.commit()

        # Second call with same raw_item_id — must not raise
        with session_factory() as session:
            queue_for_classification(session, raw_item_id, "цемент снова")
            session.commit()

        with session_factory() as session:
            count = session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM manual_classification_queue WHERE raw_item_id = :id"
                ),
                {"id": raw_item_id},
            ).scalar()

        assert count == 1, (
            f"Idempotent queue_for_classification must leave exactly 1 row, got {count}"
        )

    def test_queue_does_not_increment_consecutive_failures(
        self, migrated_seeded_db
    ) -> None:
        """queue_for_classification never modifies sources.consecutive_failures (REQ-uzex-parser)."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import queue_for_classification  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)

        # Insert a source + raw_item
        with session_factory() as session:
            source_row = session.execute(
                sa.text(
                    """
                    INSERT INTO sources (kind, adapter, name, url, is_enabled, consecutive_failures)
                    VALUES ('exchange', 'test_adapter3', 'Test Source 3', NULL, false, 0)
                    RETURNING id
                    """
                )
            ).fetchone()
            source_id = source_row[0]

            raw_row = session.execute(
                sa.text(
                    """
                    INSERT INTO raw_items (source_id, content_hash, parse_status)
                    VALUES (:source_id, '\\x03'::bytea, 'pending')
                    RETURNING id
                    """
                ),
                {"source_id": source_id},
            ).fetchone()
            raw_item_id = raw_row[0]
            session.commit()

        # Queue the item
        with session_factory() as session:
            queue_for_classification(session, raw_item_id, "неизвестный товар")
            session.commit()

        # Verify consecutive_failures is still 0
        with session_factory() as session:
            failures = session.execute(
                sa.text(
                    "SELECT consecutive_failures FROM sources WHERE id = :id"
                ),
                {"id": source_id},
            ).scalar()

        assert failures == 0, (
            f"queue_for_classification must NOT increment consecutive_failures, got {failures}"
        )

    def test_queue_truncates_product_text_to_512(self, migrated_seeded_db) -> None:
        """product_text is truncated to 512 chars (T-02-05: DoS via oversized text)."""
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services.relevance_service import queue_for_classification  # noqa: PLC0415

        session_factory = sessionmaker(bind=migrated_seeded_db)

        # Insert a raw_item to FK-reference
        with session_factory() as session:
            source_row = session.execute(
                sa.text(
                    """
                    INSERT INTO sources (kind, adapter, name, url, is_enabled, consecutive_failures)
                    VALUES ('exchange', 'test_adapter4', 'Test Source 4', NULL, false, 0)
                    RETURNING id
                    """
                )
            ).fetchone()
            source_id = source_row[0]

            raw_row = session.execute(
                sa.text(
                    """
                    INSERT INTO raw_items (source_id, content_hash, parse_status)
                    VALUES (:source_id, '\\x04'::bytea, 'pending')
                    RETURNING id
                    """
                ),
                {"source_id": source_id},
            ).fetchone()
            raw_item_id = raw_row[0]
            session.commit()

        oversized_text = "а" * 600  # 600 chars > 512
        with session_factory() as session:
            queue_for_classification(session, raw_item_id, oversized_text)
            session.commit()

            stored_text = session.execute(
                sa.text(
                    "SELECT product_text FROM manual_classification_queue WHERE raw_item_id = :id"
                ),
                {"id": raw_item_id},
            ).scalar()

        assert stored_text is not None
        assert len(stored_text) <= 512, (
            f"product_text must be truncated to ≤512 chars, got {len(stored_text)}"
        )
