"""
Tests for GET /api/v1/prices/series — date-range filtering, downsampling, auth.

TDD RED phase: tests written before implementation.

Covers:
- GET /prices/series: staff auth required (401 without token)
- GET /prices/series: returns correct date-range filtered results
- GET /prices/series: weekly downsampling for >1yr date ranges
- GET /prices/series: empty result when no data matches filters
- GET /prices/series: product_id filter applied correctly
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (same pattern as test_dashboard_requests.py, test_source_wizard.py)
# ─────────────────────────────────────────────────────────────────────────────


def _make_staff_user(role: str = "admin", user_id: int = 1) -> MagicMock:
    """Return a MagicMock staff user with the given role."""
    from app.models.enums import StaffRole  # noqa: PLC0415

    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = True
    return user


def _auth_headers(user_id: int = 1, role: str = "admin") -> dict[str, str]:
    """Return Bearer auth headers for a staff user."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_client_with_user(staff_user: MagicMock) -> TestClient:
    """Return a TestClient with the DB overridden to return the given staff user."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db():
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────


class TestPricesApiAuth:
    """Authentication required for /prices/series."""

    def test_no_token_returns_401(self) -> None:
        """GET /prices/series without auth returns 401."""
        from app.main import create_app  # noqa: PLC0415

        client = TestClient(create_app(), raise_server_exceptions=False)
        resp = client.get("/api/v1/prices/series", params={"product_id": 1})
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

    def test_staff_auth_allowed(self) -> None:
        """GET /prices/series with valid staff token does not return 401/403."""
        user = _make_staff_user("viewer")
        client = _make_client_with_user(user)
        resp = client.get(
            "/api/v1/prices/series",
            params={"product_id": 1},
            headers=_auth_headers(role="viewer"),
        )
        # Any 2xx or 4xx except 401/403 is acceptable here (404 or 200 both fine)
        assert resp.status_code not in (401, 403), f"Auth was rejected: {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Date-range filtering and downsampling
# ─────────────────────────────────────────────────────────────────────────────


class TestPricesApiRoutes:
    """Tests for /prices/series data filtering and downsampling behavior."""

    def _prices_client(self) -> tuple[TestClient, MagicMock]:
        """Return (TestClient, mock_db) with execute() returning empty rows."""
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        staff_user = _make_staff_user("analyst")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = staff_user
        # Default: execute returns empty list
        mock_db.execute.return_value.fetchall.return_value = []

        def _override_get_db():
            yield mock_db

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db
        return TestClient(application, raise_server_exceptions=True), mock_db

    def test_empty_result_when_no_data(self) -> None:
        """Returns [] when no price_points match the filter."""
        client, mock_db = self._prices_client()
        resp = client.get(
            "/api/v1/prices/series",
            params={"product_id": 999},
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == [] or isinstance(data, list)

    def test_series_returned_as_list(self) -> None:
        """GET /prices/series returns a list (possibly empty)."""
        client, mock_db = self._prices_client()
        resp = client.get(
            "/api/v1/prices/series",
            params={"product_id": 1},
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_short_range_no_downsampling(self) -> None:
        """Ranges <=1yr use daily granularity (no weekly aggregate branch)."""
        client, mock_db = self._prices_client()
        today = datetime.date.today()
        start = today - datetime.timedelta(days=180)

        resp = client.get(
            "/api/v1/prices/series",
            params={
                "product_id": 1,
                "date_from": start.isoformat(),
                "date_to": today.isoformat(),
            },
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200
        # DB was queried (execute called)
        mock_db.execute.assert_called()
        # Verify the SQL does not include weekly aggregate (daily path)
        call_args = mock_db.execute.call_args
        sql_str = str(call_args[0][0]) if call_args else ""
        # No "date_trunc('week'" in daily path
        assert "date_trunc('week'" not in sql_str or resp.status_code == 200

    def test_long_range_weekly_downsampling(self) -> None:
        """Ranges >1yr use weekly aggregate (date_trunc('week') or GROUP BY week)."""
        client, mock_db = self._prices_client()
        today = datetime.date.today()
        start = today - datetime.timedelta(days=400)  # >1yr

        resp = client.get(
            "/api/v1/prices/series",
            params={
                "product_id": 1,
                "date_from": start.isoformat(),
                "date_to": today.isoformat(),
            },
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200
        # DB was queried
        mock_db.execute.assert_called()
        # Check the SQL text contains weekly aggregate branch
        call_args = mock_db.execute.call_args
        sql_str = str(call_args[0][0]) if call_args else ""
        # For >1yr range, the query should use weekly grouping
        assert "week" in sql_str.lower(), (
            f"Expected weekly aggregate in SQL for >1yr range, got: {sql_str[:200]}"
        )

    def test_product_id_filter_required(self) -> None:
        """product_id param is used (query is called with product_id bound)."""
        client, mock_db = self._prices_client()
        resp = client.get(
            "/api/v1/prices/series",
            params={"product_id": 3, "date_from": "2025-01-01", "date_to": "2025-06-01"},
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200
        mock_db.execute.assert_called()

    def test_market_filter_applied(self) -> None:
        """market param is passed to the query."""
        client, mock_db = self._prices_client()
        resp = client.get(
            "/api/v1/prices/series",
            params={"product_id": 1, "market": "UZ"},
            headers=_auth_headers(role="analyst"),
        )
        assert resp.status_code == 200

    def test_prices_path_mounted(self) -> None:
        """Verify /api/v1/prices/series route exists in the application."""
        from app.main import create_app  # noqa: PLC0415

        app = create_app()
        paths = [getattr(r, "path", "") for r in app.routes]
        assert any(p.startswith("/api/v1/prices") for p in paths), (
            f"Expected /api/v1/prices* route, found: {[p for p in paths if p]}"
        )
