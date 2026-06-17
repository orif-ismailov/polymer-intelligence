"""
Tests for GET /requests/export — CSV stream endpoint (Phase 4, Plan 05).

Asserts:
- Response content-type: text/csv
- Content-Disposition: attachment; filename=requests.csv
- Streamed body contains a header row + at least one data row given a mocked result set.
- Endpoint is guarded by get_current_staff_user (401 without Bearer token).
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ── Helpers (copied from test_dashboard_requests.py) ──────────────────────────

def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    return db


def _make_staff_user(role: str, user_id: int = 1) -> MagicMock:
    from app.models.enums import StaffRole  # noqa: PLC0415
    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = True
    return user


def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    from app.core.security import create_access_token  # noqa: PLC0415
    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_mock_request(id: int = 1) -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object for CSV export."""
    from app.models.enums import RequestStatus  # noqa: PLC0415
    import datetime  # noqa: PLC0415

    req = MagicMock()
    req.id = id
    req.number = f"REQ-2026-06-17-{id:05d}"
    req.status = RequestStatus.new
    req.product_id = 1
    req.grade_text = "HDPE 2420D"
    req.polymer_type = "HDPE"
    req.volume = 100
    req.volume_unit = "MT"
    req.target_price = 1200
    req.currency = "USD"
    req.urgency = "medium"
    req.assigned_to = None
    req.created_at = datetime.datetime(2026, 6, 17, 10, 0, 0)
    req.updated_at = datetime.datetime(2026, 6, 17, 10, 0, 0)
    return req


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRequestsExportContentType:
    """GET /requests/export returns text/csv with attachment header."""

    def _make_client(self, staff_user: MagicMock, requests: list) -> "TestClient":  # type: ignore[return]
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_db = MagicMock()
        # Auth query: filter().first() → staff_user
        mock_db.query.return_value.filter.return_value.first.return_value = staff_user
        # Export query chain: .order_by().filter()*.limit() → iterable of requests
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = iter(requests)

        def _query_side_effect(model):
            from app.models.staff import StaffUser  # noqa: PLC0415
            from app.models.requests import Request  # noqa: PLC0415
            if model is StaffUser:
                q = MagicMock()
                q.filter.return_value.first.return_value = staff_user
                return q
            # Request model — return the export mock_query
            return mock_query

        mock_db.query.side_effect = _query_side_effect

        def _override_get_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = _override_get_db
        return TestClient(app, raise_server_exceptions=True)

    def test_export_returns_text_csv_content_type(self):
        """GET /requests/export returns Content-Type: text/csv."""
        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=1)
        client = self._make_client(admin_user, [req])

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/export", headers=headers)

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_returns_attachment_content_disposition(self):
        """GET /requests/export includes Content-Disposition attachment header."""
        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=1)
        client = self._make_client(admin_user, [req])

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/export", headers=headers)

        assert response.status_code == 200
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition
        assert "requests.csv" in content_disposition

    def test_export_body_has_header_row(self):
        """Streamed CSV body has a header row with expected column names."""
        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=1)
        client = self._make_client(admin_user, [req])

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/export", headers=headers)

        assert response.status_code == 200
        lines = response.text.strip().splitlines()
        assert len(lines) >= 1
        header_row = lines[0]
        # Must contain key column names
        assert "id" in header_row
        assert "number" in header_row
        assert "status" in header_row

    def test_export_body_has_at_least_one_data_row(self):
        """Given a non-empty mock result set, CSV has header + data row(s)."""
        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=42)
        client = self._make_client(admin_user, [req])

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/export", headers=headers)

        assert response.status_code == 200
        lines = [l for l in response.text.strip().splitlines() if l.strip()]
        # At least 2 lines: header + 1 data row
        assert len(lines) >= 2
        # Data row must contain the mocked id
        assert "42" in lines[1]

    def test_export_empty_result_has_only_header(self):
        """When no requests match filters, CSV has only the header row."""
        admin_user = _make_staff_user("admin", user_id=1)
        client = self._make_client(admin_user, [])  # empty

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/export", headers=headers)

        assert response.status_code == 200
        lines = [l for l in response.text.strip().splitlines() if l.strip()]
        # Only header row
        assert len(lines) == 1


class TestRequestsExportAuth:
    """GET /requests/export is guarded by get_current_staff_user."""

    def test_export_returns_401_without_auth(self):
        """GET /requests/export returns 401 without a Bearer token."""
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/v1/requests/export")
        assert response.status_code == 401
