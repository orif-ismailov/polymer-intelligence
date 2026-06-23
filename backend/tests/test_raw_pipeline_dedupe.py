"""
Tests for raw_pipeline deduplicated insert.

These tests use a live-DB guard: they are skipped if DATABASE_URL env var
points to a test/mock URL or if a live PostgreSQL connection is unavailable.
The guard prevents the tests from accidentally failing in CI without a DB.

Coverage:
- compute_content_hash: determinism (same triple → same 32-byte digest)
- save_raw_items: N rows on first call, 0 on identical second call (ON CONFLICT DO NOTHING)
- Immutability: no UPDATE on raw_items content/payload between runs
- parse_status defaults to 'pending'

Run with a live DB:
    DATABASE_URL=postgresql+psycopg://... pytest tests/test_raw_pipeline_dedupe.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest

# ── Live-DB guard ─────────────────────────────────────────────────────────────
_DB_URL = os.environ.get("DATABASE_URL", "")
_REQUIRES_LIVE_DB = pytest.mark.skipif(
    not _DB_URL or "localhost" not in _DB_URL and "postgres" not in _DB_URL,
    reason="Skipped: no live PostgreSQL DATABASE_URL configured",
)


# ── Unit tests (no DB required) ───────────────────────────────────────────────


class TestComputeContentHash:
    """compute_content_hash must be deterministic and return 32 bytes."""

    def test_deterministic_same_inputs(self) -> None:
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id="lot-42", content="foo bar")
        h2 = compute_content_hash(source_id=1, external_id="lot-42", content="foo bar")
        assert h1 == h2, "same inputs must produce identical bytes"

    def test_returns_32_bytes(self) -> None:
        from app.services.raw_pipeline import compute_content_hash

        h = compute_content_hash(source_id=99, external_id="x", content="test content")
        assert isinstance(h, bytes)
        assert len(h) == 32, f"SHA-256 digest must be 32 bytes, got {len(h)}"

    def test_different_content_different_hash(self) -> None:
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id="id", content="content A")
        h2 = compute_content_hash(source_id=1, external_id="id", content="content B")
        assert h1 != h2

    def test_different_source_id_different_hash(self) -> None:
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id="id", content="content")
        h2 = compute_content_hash(source_id=2, external_id="id", content="content")
        assert h1 != h2

    def test_different_external_id_different_hash(self) -> None:
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id="lot-1", content="content")
        h2 = compute_content_hash(source_id=1, external_id="lot-2", content="content")
        assert h1 != h2

    def test_none_external_id_handled(self) -> None:
        """external_id=None must not crash and must be deterministic."""
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id=None, content="content")
        h2 = compute_content_hash(source_id=1, external_id=None, content="content")
        assert h1 == h2
        assert len(h1) == 32

    def test_whitespace_normalization(self) -> None:
        """Content with equivalent whitespace must hash the same."""
        from app.services.raw_pipeline import compute_content_hash

        h1 = compute_content_hash(source_id=1, external_id="id", content="foo  bar")
        h2 = compute_content_hash(source_id=1, external_id="id", content="foo bar")
        # Both should hash the same after whitespace collapse
        assert h1 == h2


# ── Integration tests (require live PostgreSQL) ────────────────────────────────


@_REQUIRES_LIVE_DB
class TestSaveRawItemsDeduplication:
    """Integration: save_raw_items inserts N rows on first call, 0 on re-run."""

    @pytest.fixture(autouse=True)
    def _skip_without_live_db(self) -> None:
        """Extra guard: attempt DB import; skip if it fails."""
        try:
            from app.core.db import engine  # noqa: F401, PLC0415
        except Exception as exc:
            pytest.skip(f"Cannot import DB engine: {exc}")

    def _make_source(self, session: object) -> object:
        """Insert a temporary Source row and return it."""
        import sqlalchemy as sa  # noqa: PLC0415

        from app.models.enums import SourceKind  # noqa: PLC0415

        unique_name = f"test_raw_pipeline_{uuid.uuid4().hex[:8]}"
        session.execute(  # type: ignore[attr-defined]
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, is_enabled, config, created_at)
                VALUES (:kind, :adapter, :name, true, '{}', NOW())
                """
            ),
            {
                "kind": SourceKind.exchange.value,
                "adapter": "uzex_offers",
                "name": unique_name,
            },
        )
        session.execute(sa.text("COMMIT"))  # type: ignore[attr-defined]
        row = session.execute(  # type: ignore[attr-defined]
            sa.text("SELECT id FROM sources WHERE name = :name"),
            {"name": unique_name},
        ).fetchone()
        assert row is not None
        return row[0]

    def _delete_source(self, session: object, source_id: int) -> None:
        """Clean up: delete raw_items and source rows created by the test."""
        import sqlalchemy as sa  # noqa: PLC0415

        session.execute(  # type: ignore[attr-defined]
            sa.text("DELETE FROM raw_items WHERE source_id = :sid"),
            {"sid": source_id},
        )
        session.execute(  # type: ignore[attr-defined]
            sa.text("DELETE FROM sources WHERE id = :id"),
            {"id": source_id},
        )
        session.execute(sa.text("COMMIT"))  # type: ignore[attr-defined]

    def test_first_call_inserts_n_rows(self) -> None:
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.core.db import engine  # noqa: PLC0415
        from app.ingest.base import RawItemDraft  # noqa: PLC0415
        from app.models.sources import Source  # noqa: PLC0415
        from app.services.raw_pipeline import save_raw_items  # noqa: PLC0415

        with Session(engine) as session:
            source_id = self._make_source(session)
            try:
                source = session.get(Source, source_id)
                assert source is not None

                drafts = [
                    RawItemDraft(
                        external_id=f"lot-{i}",
                        content=f"product {i}; price: 100",
                        payload={"product_text": f"product {i}", "price": "100"},
                        event_at=None,
                    )
                    for i in range(3)
                ]

                count, inserted_ids = save_raw_items(session, source, drafts)
                session.commit()

                assert count == 3, f"Expected 3 inserted, got {count}"
                assert len(inserted_ids) == 3, (
                    f"Expected 3 inserted_ids, got {inserted_ids}"
                )
            finally:
                self._delete_source(session, source_id)

    def test_second_call_inserts_zero_rows(self) -> None:
        """Identical second call must return 0 (ON CONFLICT DO NOTHING)."""
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.core.db import engine  # noqa: PLC0415
        from app.ingest.base import RawItemDraft  # noqa: PLC0415
        from app.models.sources import Source  # noqa: PLC0415
        from app.services.raw_pipeline import save_raw_items  # noqa: PLC0415

        with Session(engine) as session:
            source_id = self._make_source(session)
            try:
                source = session.get(Source, source_id)
                assert source is not None

                drafts = [
                    RawItemDraft(
                        external_id=f"lot-dedupe-{i}",
                        content=f"product {i}; price: 200",
                        payload={"product_text": f"product {i}", "price": "200"},
                        event_at=None,
                    )
                    for i in range(2)
                ]

                count1, ids1 = save_raw_items(session, source, drafts)
                session.commit()

                # Re-run with identical drafts
                count2, ids2 = save_raw_items(session, source, drafts)
                session.commit()

                assert count1 == 2, f"First call should insert 2, got {count1}"
                assert len(ids1) == 2, f"First call should return 2 IDs, got {ids1}"
                assert count2 == 0, f"Second call should insert 0, got {count2}"
                assert ids2 == [], f"Second call should return empty IDs, got {ids2}"
            finally:
                self._delete_source(session, source_id)

    def test_row_count_unchanged_after_second_call(self) -> None:
        """Total raw_items for source must not change on duplicate save."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.core.db import engine  # noqa: PLC0415
        from app.ingest.base import RawItemDraft  # noqa: PLC0415
        from app.models.sources import Source  # noqa: PLC0415
        from app.services.raw_pipeline import save_raw_items  # noqa: PLC0415

        with Session(engine) as session:
            source_id = self._make_source(session)
            try:
                source = session.get(Source, source_id)
                assert source is not None

                drafts = [
                    RawItemDraft(
                        external_id=f"count-check-{i}",
                        content=f"item {i}; vol: 50",
                        payload={"product_text": f"item {i}", "volume": "50"},
                        event_at=None,
                    )
                    for i in range(4)
                ]

                _count, _ids = save_raw_items(session, source, drafts)
                session.commit()

                count_before = session.execute(
                    sa.text("SELECT COUNT(*) FROM raw_items WHERE source_id = :sid"),
                    {"sid": source_id},
                ).scalar()

                # Save same drafts again
                _count2, _ids2 = save_raw_items(session, source, drafts)
                session.commit()

                count_after = session.execute(
                    sa.text("SELECT COUNT(*) FROM raw_items WHERE source_id = :sid"),
                    {"sid": source_id},
                ).scalar()

                assert count_before == count_after, (
                    f"Row count changed: {count_before} → {count_after}"
                )
                assert count_before == 4
            finally:
                self._delete_source(session, source_id)

    def test_parse_status_defaults_to_pending(self) -> None:
        """Newly inserted raw_items must have parse_status='pending'."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.core.db import engine  # noqa: PLC0415
        from app.ingest.base import RawItemDraft  # noqa: PLC0415
        from app.models.sources import Source  # noqa: PLC0415
        from app.services.raw_pipeline import save_raw_items  # noqa: PLC0415

        with Session(engine) as session:
            source_id = self._make_source(session)
            try:
                source = session.get(Source, source_id)
                assert source is not None

                drafts = [
                    RawItemDraft(
                        external_id="status-check",
                        content="product status; price: 300",
                        payload={"product_text": "product status", "price": "300"},
                        event_at=None,
                    )
                ]

                _count, _ids = save_raw_items(session, source, drafts)
                session.commit()

                row = session.execute(
                    sa.text(
                        "SELECT parse_status FROM raw_items WHERE source_id = :sid LIMIT 1"
                    ),
                    {"sid": source_id},
                ).fetchone()

                assert row is not None
                assert str(row[0]) == "pending", f"Expected pending, got {row[0]}"
            finally:
                self._delete_source(session, source_id)


# ── No-UPDATE immutability check (static analysis proxy) ─────────────────────


class TestImmutabilityContract:
    """Verify that raw_pipeline.py never issues UPDATE on raw_items content/payload."""

    def test_no_update_raw_items_in_source(self) -> None:
        """grep-equivalent check: no UPDATE targeting raw_items content/payload."""
        import pathlib  # noqa: PLC0415
        import re  # noqa: PLC0415

        pipeline_path = (
            pathlib.Path(__file__).parent.parent
            / "app"
            / "services"
            / "raw_pipeline.py"
        )
        source = pipeline_path.read_text(encoding="utf-8")

        # Check that there's no literal UPDATE raw_items statement
        update_pattern = re.compile(
            r"UPDATE\s+raw_items",
            re.IGNORECASE,
        )
        matches = update_pattern.findall(source)
        assert not matches, (
            f"raw_pipeline.py must not UPDATE raw_items — found: {matches}"
        )

    def test_no_not_yet_implemented_in_ingest_tasks(self) -> None:
        """Verify placeholders are replaced: no not_yet_implemented in ingest.py."""
        import pathlib  # noqa: PLC0415

        ingest_path = (
            pathlib.Path(__file__).parent.parent / "app" / "tasks" / "ingest.py"
        )
        source = ingest_path.read_text(encoding="utf-8")
        assert "not_yet_implemented" not in source, (
            "app/tasks/ingest.py still contains 'not_yet_implemented' placeholder text"
        )
