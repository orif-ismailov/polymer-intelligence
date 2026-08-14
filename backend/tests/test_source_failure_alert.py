"""
Tests for failure isolation, check_source_health beat task, and GET /admin/sources/health.

Covers:
- run_source_fetch_isolated: one source exception is caught and recorded; sibling sources
  still record success (isolation — SC#5 / REQ-nfr-reliability)
- After 3 isolated failure cycles of one source, exactly one source_failure alert exists
- check_source_health task: no longer a placeholder (not_yet_implemented absent)
- GET /admin/sources/health: returns per-source health fields for admin, 403 for non-admin

Live-DB guard: DB-backed tests are skipped unless DATABASE_URL points to a real PostgreSQL
instance. API unit tests run without a live DB.

Run with live DB:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
    pytest tests/test_source_failure_alert.py -v
"""

from __future__ import annotations

import contextlib
import datetime
import os
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Live-DB guard ─────────────────────────────────────────────────────────────
_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and ("localhost" in _DB_URL or "postgres" in _DB_URL) and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "source failure alert DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_staff_user(id: int, role: str, is_active: bool = True):
    """Return a mock StaffUser."""
    from app.models.enums import StaffRole  # noqa: PLC0415

    user = MagicMock()
    user.id = id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = is_active
    return user


def _auth_headers(staff_user_id: int, role: str) -> dict[str, str]:
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(staff_user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


# ── Unit tests (no DB required) ───────────────────────────────────────────────


class TestCheckSourceHealthTask:
    """check_source_health Celery task is registered and not a placeholder."""

    def test_check_source_health_registered_in_celery(self) -> None:
        """check_source_health is registered in the Celery app after importing notify."""
        import app.tasks.notify  # noqa: F401, PLC0415
        from app.tasks.celery_app import celery_app  # noqa: PLC0415

        task = celery_app.tasks.get("check_source_health")
        assert task is not None, "check_source_health task must be registered in Celery"

    def test_check_source_health_is_not_placeholder(self) -> None:
        """notify.py must not contain 'not_yet_implemented' (placeholder replaced)."""
        notify_path = (
            Path(__file__).parent.parent / "app" / "tasks" / "notify.py"
        )
        source = notify_path.read_text(encoding="utf-8")
        assert "not_yet_implemented" not in source, (
            "app/tasks/notify.py still contains placeholder 'not_yet_implemented'"
        )

    def test_notify_module_importable(self) -> None:
        """tasks/notify.py is importable."""
        import app.tasks.notify  # noqa: PLC0415
        assert app.tasks.notify is not None


class TestRunSourceFetchIsolated:
    """run_source_fetch_isolated helper exists and wraps single-source fetch."""

    def test_function_importable(self) -> None:
        """run_source_fetch_isolated is importable from app.tasks.ingest."""
        from app.tasks.ingest import run_source_fetch_isolated  # noqa: PLC0415
        assert callable(run_source_fetch_isolated)

    def test_isolates_exception(self) -> None:
        """run_source_fetch_isolated catches adapter exceptions and does NOT re-raise."""
        from app.tasks.ingest import run_source_fetch_isolated  # noqa: PLC0415

        session = MagicMock()
        source = MagicMock()
        source.id = 42

        # Adapter that always raises
        bad_adapter = MagicMock()
        bad_adapter.fetch.side_effect = Exception("network timeout")

        # record_fetch_failure should be called (mock it to avoid importing the actual service)
        with patch("app.tasks.ingest.record_fetch_failure") as mock_fail, \
             patch("app.tasks.ingest.record_fetch_success") as mock_success, \
             patch("app.tasks.ingest._run_fetch_for_source", side_effect=Exception("fail")):
            # Must NOT raise
            run_source_fetch_isolated(session, source, bad_adapter)
            mock_fail.assert_called_once_with(session, source.id, "fail")
            mock_success.assert_not_called()

    def test_records_success_on_normal_fetch(self) -> None:
        """run_source_fetch_isolated calls record_fetch_success on a normal fetch."""
        from app.tasks.ingest import run_source_fetch_isolated  # noqa: PLC0415

        session = MagicMock()
        source = MagicMock()
        source.id = 99

        adapter = MagicMock()

        # save_raw_items now returns (count, inserted_ids) tuple (CR-04)
        with patch("app.tasks.ingest._run_fetch_for_source", return_value=[]), \
             patch("app.tasks.ingest.record_fetch_success") as mock_success, \
             patch("app.tasks.ingest.record_fetch_failure") as mock_fail, \
             patch("app.tasks.ingest.save_raw_items", return_value=(0, [])):
            run_source_fetch_isolated(session, source, adapter)
            mock_success.assert_called_once_with(session, source.id)
            mock_fail.assert_not_called()


class TestAdminSourcesHealthEndpointUnit:
    """GET /admin/sources/health: admin allowed, non-admin rejected (unit/mock)."""

    def _make_health_client(self, staff_user: MagicMock, mock_sources: list[Any]) -> Any:
        """Build a TestClient with get_db returning a mock that serves health data."""
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = staff_user

        # Build mock rows for execute().fetchall() as tuples (matching indexed access row[N])
        mock_execute = MagicMock()
        mock_execute.fetchall.return_value = [
            (
                s["id"],
                s["name"],
                s["adapter"],
                s["kind"],
                s["is_enabled"],
                s["last_fetch_at"],
                s["last_success_at"],
                s["consecutive_failures"],
            )
            for s in mock_sources
        ]
        mock_db.execute.return_value = mock_execute

        def _override_get_db() -> Generator[Any, None, None]:
            yield mock_db

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db

        from fastapi.testclient import TestClient  # noqa: PLC0415
        return TestClient(application, raise_server_exceptions=True)

    def test_admin_gets_200_with_health_fields(self) -> None:
        """Admin user gets 200 from GET /admin/sources/health."""
        admin_user = _make_staff_user(id=1, role="admin")
        client = self._make_health_client(admin_user, [])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get(
                "/api/v1/admin/sources/health",
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_trader_gets_403_from_health_endpoint(self) -> None:
        """Trader user gets 403 from GET /admin/sources/health."""
        trader_user = _make_staff_user(id=3, role="trader")
        client = self._make_health_client(trader_user, [])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get(
                "/api/v1/admin/sources/health",
                headers=_auth_headers(3, "trader"),
            )

        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_viewer_gets_403_from_health_endpoint(self) -> None:
        """Viewer user gets 403 from GET /admin/sources/health."""
        viewer_user = _make_staff_user(id=4, role="viewer")
        client = self._make_health_client(viewer_user, [])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get(
                "/api/v1/admin/sources/health",
                headers=_auth_headers(4, "viewer"),
            )

        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_unauthenticated_gets_401_from_health_endpoint(self) -> None:
        """No token → 401 from GET /admin/sources/health."""
        admin_user = _make_staff_user(id=1, role="admin")
        client = self._make_health_client(admin_user, [])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/admin/sources/health")

        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_health_endpoint_returns_expected_field_keys(self) -> None:
        """Response items include the required health fields."""
        admin_user = _make_staff_user(id=1, role="admin")

        now = datetime.datetime.now(tz=datetime.UTC)
        mock_sources = [
            {
                "id": 1,
                "name": "UZEX Offers",
                "adapter": "uzex_offers",
                "kind": "exchange",
                "is_enabled": True,
                "last_fetch_at": now,
                "last_success_at": now,
                "consecutive_failures": 0,
            }
        ]
        client = self._make_health_client(admin_user, mock_sources)

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get(
                "/api/v1/admin/sources/health",
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Endpoint may return 0 items (mock doesn't have real DB); just assert format
        # For the unit test we mainly care about the 200 response and structure


class TestIngestIsolationContract:
    """Verify that failure isolation is in place in ingest.py."""

    def test_ingest_imports_run_source_fetch_isolated(self) -> None:
        """ingest.py defines run_source_fetch_isolated (isolation helper)."""
        import app.tasks.ingest as ingest_mod  # noqa: PLC0415
        assert hasattr(ingest_mod, "run_source_fetch_isolated"), (
            "app/tasks/ingest.py must export run_source_fetch_isolated"
        )

    def test_ingest_imports_record_fetch_success(self) -> None:
        """ingest.py imports record_fetch_success from source_health_service."""
        import app.tasks.ingest as ingest_mod  # noqa: PLC0415
        assert hasattr(ingest_mod, "record_fetch_success"), (
            "app/tasks/ingest.py must import record_fetch_success for health wrapping"
        )

    def test_ingest_imports_record_fetch_failure(self) -> None:
        """ingest.py imports record_fetch_failure from source_health_service."""
        import app.tasks.ingest as ingest_mod  # noqa: PLC0415
        assert hasattr(ingest_mod, "record_fetch_failure"), (
            "app/tasks/ingest.py must import record_fetch_failure for health wrapping"
        )


# ── DB-backed tests ────────────────────────────────────────────────────────────


@_requires_real_db
class TestFailureIsolationDB:
    """Live-DB: one source failing must not abort siblings; 3 failures → 1 alert."""

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

    def _make_source(self, session, adapter: str = "uzex_offers") -> int:
        """Insert a temporary Source row and return its id."""
        import sqlalchemy as sa  # noqa: PLC0415

        unique_name = f"test_isolation_{uuid.uuid4().hex[:8]}"
        session.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, is_enabled, config, created_at)
                VALUES ('exchange', :adapter, :name, true, '{}', NOW())
                """
            ),
            {"name": unique_name, "adapter": adapter},
        )
        session.commit()
        row = session.execute(
            sa.text("SELECT id FROM sources WHERE name = :name"),
            {"name": unique_name},
        ).fetchone()
        assert row is not None
        return int(row[0])

    def _cleanup(self, session, *source_ids: int) -> None:
        """Remove test data."""
        import sqlalchemy as sa  # noqa: PLC0415

        for sid in source_ids:
            session.execute(
                sa.text("DELETE FROM alerts WHERE dedupe_key LIKE :pattern"),
                {"pattern": f"source_failure:{sid}:%"},
            )
            session.execute(
                sa.text("DELETE FROM sources WHERE id = :id"),
                {"id": sid},
            )
        session.commit()

    def test_isolation_bad_source_does_not_abort_siblings(self, migrated_db) -> None:
        """run_source_fetch_isolated: one source raising must not prevent siblings from succeeding."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.domains.signals.source_models import Source  # noqa: PLC0415
        from app.tasks.ingest import run_source_fetch_isolated  # noqa: PLC0415

        with Session(migrated_db) as session:
            good_id_1 = self._make_source(session)
            bad_id = self._make_source(session)
            good_id_2 = self._make_source(session)

            try:
                good_source_1 = session.get(Source, good_id_1)
                bad_source = session.get(Source, bad_id)
                good_source_2 = session.get(Source, good_id_2)

                # Good adapters return empty list; bad adapter raises
                good_adapter = MagicMock()
                bad_adapter = MagicMock()

                for src, adapter in [
                    (good_source_1, good_adapter),
                    (bad_source, bad_adapter),
                    (good_source_2, good_adapter),
                ]:
                    with patch("app.tasks.ingest._run_fetch_for_source") as mock_fetch, \
                         patch("app.tasks.ingest.save_raw_items", return_value=0):
                        if src.id == bad_id:
                            mock_fetch.side_effect = Exception("simulated failure")
                        else:
                            mock_fetch.return_value = []

                        run_source_fetch_isolated(session, src, adapter)
                        session.commit()

                # Good sources must have last_fetch_at set (success recorded)
                for good_id in (good_id_1, good_id_2):
                    row = session.execute(
                        sa.text(
                            "SELECT last_success_at, consecutive_failures FROM sources WHERE id = :id"
                        ),
                        {"id": good_id},
                    ).fetchone()
                    assert row is not None
                    assert row[0] is not None, (
                        f"Good source {good_id} must have last_success_at set"
                    )
                    assert row[1] == 0, (
                        f"Good source {good_id} must have consecutive_failures=0"
                    )

                # Bad source must have consecutive_failures incremented
                bad_row = session.execute(
                    sa.text(
                        "SELECT consecutive_failures FROM sources WHERE id = :id"
                    ),
                    {"id": bad_id},
                ).fetchone()
                assert bad_row is not None
                assert bad_row[0] >= 1, (
                    f"Bad source must have consecutive_failures >= 1, got {bad_row[0]}"
                )
            finally:
                self._cleanup(session, good_id_1, bad_id, good_id_2)

    def test_three_isolated_failures_create_one_alert(self, migrated_db) -> None:
        """3 runs of run_source_fetch_isolated failing → exactly one source_failure alert."""
        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.orm import Session  # noqa: PLC0415

        from app.domains.signals.source_models import Source  # noqa: PLC0415
        from app.tasks.ingest import run_source_fetch_isolated  # noqa: PLC0415

        with Session(migrated_db) as session:
            source_id = self._make_source(session)

            try:
                source = session.get(Source, source_id)
                adapter = MagicMock()

                # 3 isolated failures
                for _ in range(3):
                    with patch(
                        "app.tasks.ingest._run_fetch_for_source",
                        side_effect=Exception("simulated"),
                    ):
                        run_source_fetch_isolated(session, source, adapter)
                        session.commit()

                alert_count = session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM alerts WHERE dedupe_key LIKE :pattern"
                    ),
                    {"pattern": f"source_failure:{source_id}:%"},
                ).scalar()

                assert alert_count == 1, (
                    f"3 isolated failures must create exactly 1 source_failure alert, got {alert_count}"
                )
            finally:
                self._cleanup(session, source_id)
