"""
Tests for source_health_service: success/failure bookkeeping + 3-strike deduped alert.

Covers:
- record_fetch_success: zeroes consecutive_failures, sets last_success_at
- record_fetch_failure: increments consecutive_failures, returns new count
- raise_source_failure_alert: ON CONFLICT DO NOTHING — exactly one alert per source per day
- 3rd consecutive failure → alert created; 4th same-day → no new alert (dedupe)
- Success after failures resets counter to 0 (next failure series starts fresh)
- check_all_sources_health: idempotent scan for already-3-failing enabled sources

Live-DB guard: tests are skipped unless DATABASE_URL points to a real PostgreSQL instance.

Run with live DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_source_health.py -v
"""

from __future__ import annotations

import contextlib
import datetime
import os
import uuid
from pathlib import Path

import pytest

# ── Live-DB guard ─────────────────────────────────────────────────────────────
_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and ("localhost" in _DB_URL or "postgres" in _DB_URL) and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "source health DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


# ── Unit tests (no DB required) ───────────────────────────────────────────────


class TestSourceHealthServiceImports:
    """source_health_service module is importable and exposes required symbols."""

    def test_module_importable(self) -> None:
        """source_health_service is importable without a live DB."""
        from app.services import source_health_service  # noqa: PLC0415
        assert source_health_service is not None

    def test_exports_record_fetch_success(self) -> None:
        from app.services.source_health_service import record_fetch_success  # noqa: PLC0415
        assert callable(record_fetch_success)

    def test_exports_record_fetch_failure(self) -> None:
        from app.services.source_health_service import record_fetch_failure  # noqa: PLC0415
        assert callable(record_fetch_failure)

    def test_exports_raise_source_failure_alert(self) -> None:
        from app.services.source_health_service import raise_source_failure_alert  # noqa: PLC0415
        assert callable(raise_source_failure_alert)

    def test_exports_check_all_sources_health(self) -> None:
        from app.services.source_health_service import check_all_sources_health  # noqa: PLC0415
        assert callable(check_all_sources_health)


# ── DB-backed tests ────────────────────────────────────────────────────────────


@_requires_real_db
class TestSourceHealthDB:
    """Live-DB integration tests for source_health_service."""

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

    def _make_source(self, session, unique_suffix: str | None = None) -> int:
        """Insert a temporary Source row and return its id."""
        import sqlalchemy as sa  # noqa: PLC0415

        unique_name = f"test_health_{unique_suffix or uuid.uuid4().hex[:8]}"
        session.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, is_enabled, config, created_at)
                VALUES ('exchange', 'uzex_offers', :name, true, '{}', NOW())
                """
            ),
            {"name": unique_name},
        )
        session.commit()
        row = session.execute(
            sa.text("SELECT id FROM sources WHERE name = :name"),
            {"name": unique_name},
        ).fetchone()
        assert row is not None
        return int(row[0])

    def _cleanup(self, session, source_id: int) -> None:
        """Remove test data."""
        import sqlalchemy as sa  # noqa: PLC0415

        # Remove dedupe alerts for this source (any date)
        session.execute(
            sa.text(
                "DELETE FROM alerts WHERE dedupe_key LIKE :pattern"
            ),
            {"pattern": f"source_failure:{source_id}:%"},
        )
        session.execute(
            sa.text("DELETE FROM sources WHERE id = :id"),
            {"id": source_id},
        )
        session.commit()

    def test_record_fetch_success_resets_counter_and_sets_timestamps(
        self, migrated_db
    ) -> None:
        """record_fetch_success sets last_fetch_at, last_success_at, and consecutive_failures=0."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import record_fetch_success  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # Pre-set consecutive_failures to 2 so we can confirm it resets
                session.execute(
                    sa.text(
                        "UPDATE sources SET consecutive_failures = 2 WHERE id = :id"
                    ),
                    {"id": source_id},
                )
                session.commit()

                before = datetime.datetime.now(tz=datetime.UTC)
                record_fetch_success(session, source_id)
                session.commit()
                after = datetime.datetime.now(tz=datetime.UTC)

                row = session.execute(
                    sa.text(
                        """
                        SELECT last_fetch_at, last_success_at, consecutive_failures
                        FROM sources WHERE id = :id
                        """
                    ),
                    {"id": source_id},
                ).fetchone()
                assert row is not None
                last_fetch_at = row[0]
                last_success_at = row[1]
                consecutive_failures = row[2]

                assert consecutive_failures == 0, (
                    f"consecutive_failures must be 0 after success, got {consecutive_failures}"
                )
                assert last_fetch_at is not None
                assert last_success_at is not None
                # Both timestamps must be close to now
                assert before <= last_fetch_at.replace(tzinfo=datetime.UTC) <= after, (
                    "last_fetch_at not in expected window"
                )
                assert before <= last_success_at.replace(tzinfo=datetime.UTC) <= after, (
                    "last_success_at not in expected window"
                )
            finally:
                self._cleanup(session, source_id)

    def test_record_fetch_failure_increments_counter(self, migrated_db) -> None:
        """record_fetch_failure increments consecutive_failures and returns the new count."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import record_fetch_failure  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # Set initial consecutive_failures to 1
                session.execute(
                    sa.text(
                        "UPDATE sources SET consecutive_failures = 1 WHERE id = :id"
                    ),
                    {"id": source_id},
                )
                session.commit()

                new_count = record_fetch_failure(session, source_id, "timeout error")
                session.commit()

                assert new_count == 2, (
                    f"Expected returned count=2 after incrementing from 1, got {new_count}"
                )

                db_row = session.execute(
                    sa.text(
                        "SELECT consecutive_failures FROM sources WHERE id = :id"
                    ),
                    {"id": source_id},
                ).fetchone()
                assert db_row is not None
                assert db_row[0] == 2, f"DB consecutive_failures must be 2, got {db_row[0]}"
            finally:
                self._cleanup(session, source_id)

    def test_three_consecutive_failures_create_exactly_one_alert(
        self, migrated_db
    ) -> None:
        """3rd consecutive failure creates exactly one source_failure alert (dedupe)."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import record_fetch_failure  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # Fail 3 times
                record_fetch_failure(session, source_id, "error 1")
                session.commit()
                record_fetch_failure(session, source_id, "error 2")
                session.commit()
                record_fetch_failure(session, source_id, "error 3")  # triggers alert
                session.commit()

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()

                assert alert_count == 1, (
                    f"Expected exactly 1 source_failure alert after 3 failures, got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)

    def test_fourth_same_day_failure_creates_no_new_alert(self, migrated_db) -> None:
        """4th failure on the same day does NOT create a duplicate alert (dedupe_key)."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import record_fetch_failure  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # Fail 4 times
                for i in range(4):
                    record_fetch_failure(session, source_id, f"error {i + 1}")
                    session.commit()

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()

                assert alert_count == 1, (
                    f"4th same-day failure must NOT create a duplicate alert; got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)

    def test_success_after_failures_resets_counter(self, migrated_db) -> None:
        """A success after failures resets consecutive_failures to 0 (next failure starts fresh)."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import (  # noqa: PLC0415
            record_fetch_failure,
            record_fetch_success,
        )

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # 2 failures, then a success, then verify reset
                record_fetch_failure(session, source_id, "err 1")
                session.commit()
                record_fetch_failure(session, source_id, "err 2")
                session.commit()
                record_fetch_success(session, source_id)
                session.commit()

                row = session.execute(
                    sa.text(
                        "SELECT consecutive_failures FROM sources WHERE id = :id"
                    ),
                    {"id": source_id},
                ).fetchone()
                assert row is not None
                assert row[0] == 0, (
                    f"consecutive_failures must be 0 after success, got {row[0]}"
                )

                # One more failure after reset — should be count=1, NOT trigger the alert
                new_count = record_fetch_failure(session, source_id, "err after reset")
                session.commit()
                assert new_count == 1, (
                    f"After reset, first failure should yield count=1, got {new_count}"
                )

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()
                assert alert_count == 0, (
                    f"Single failure after reset must NOT create alert; got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)

    def test_check_all_sources_health_is_idempotent(self, migrated_db) -> None:
        """check_all_sources_health is idempotent: running twice creates exactly one alert."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import check_all_sources_health  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                # Pre-set consecutive_failures >= 3 directly in DB
                session.execute(
                    sa.text(
                        "UPDATE sources SET consecutive_failures = 5 WHERE id = :id"
                    ),
                    {"id": source_id},
                )
                session.commit()

                # Run check twice
                check_all_sources_health(session)
                session.commit()
                check_all_sources_health(session)
                session.commit()

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()

                assert alert_count == 1, (
                    f"check_all_sources_health must be idempotent (1 alert), got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)

    def test_check_all_sources_health_only_alerts_enabled_sources(
        self, migrated_db
    ) -> None:
        """check_all_sources_health skips disabled sources even if consecutive_failures >= 3."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import check_all_sources_health  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session, unique_suffix="disabled")
            try:
                # Disable the source but set failures >= 3
                session.execute(
                    sa.text(
                        "UPDATE sources SET is_enabled = false, consecutive_failures = 5 WHERE id = :id"
                    ),
                    {"id": source_id},
                )
                session.commit()

                check_all_sources_health(session)
                session.commit()

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()

                assert alert_count == 0, (
                    f"Disabled source must NOT trigger alert; got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)

    def test_alert_has_correct_kind_and_dedupe_key(self, migrated_db) -> None:
        """The created alert has kind='source_failure' and the expected dedupe_key format."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.services.source_health_service import record_fetch_failure  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)
            try:
                for i in range(3):
                    record_fetch_failure(session, source_id, f"err {i + 1}")
                    session.commit()

                today_str = datetime.date.today().isoformat()
                expected_dedupe_key = f"source_failure:{source_id}:{today_str}"

                row = session.execute(
                    sa.text(
                        "SELECT kind, dedupe_key, severity FROM alerts WHERE dedupe_key = :dk"
                    ),
                    {"dk": expected_dedupe_key},
                ).fetchone()

                assert row is not None, f"Alert with dedupe_key={expected_dedupe_key!r} not found"
                assert row[0] == "source_failure", f"Alert kind must be 'source_failure', got {row[0]}"
                assert row[1] == expected_dedupe_key
                assert row[2] == "warning", f"Alert severity must be 'warning', got {row[2]}"
            finally:
                self._cleanup(session, source_id)
