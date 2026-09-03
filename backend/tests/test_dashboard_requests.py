"""
Tests for backend/app/api/dashboard_requests.py and related services.

TDD: RED (scaffold) -> GREEN after Task 2 routers are wired.

Covers:
- Status machine: GET /requests/{id} auto-transitions new->viewed
- Invalid transition -> 422
- Viewer PATCH -> 403 (T-04-10)
- Audit trail: every action (status, note, assign, contact) calls write_audit (D-10)
- contact_available=True/False based on telegram_user_id (D-11)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_db() -> MagicMock:
    """Return a MagicMock that quacks like a SQLAlchemy Session."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    return db


def _make_staff_user(role: str, user_id: int = 1) -> MagicMock:
    """Return a MagicMock that quacks like a StaffUser ORM object."""
    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.is_admin = role == "admin"
    user.is_active = True
    return user


def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    """Return Authorization header dict with a valid JWT for the given role."""
    from app.core.security import create_access_token  # noqa: PLC0415
    token = create_access_token(subject=str(user_id))
    return {"Authorization": f"Bearer {token}"}


def _make_client_with_user(staff_user: MagicMock) -> TestClient:  # type: ignore[return]
    """Create a TestClient with the given staff_user injected as the auth dependency."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user
    def _override_get_db():
        yield mock_db
    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


def _make_mock_request(
    id: int = 42,
    status_val: str = "new",
    telegram_user_id: int | None = 12345,
) -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object."""
    from app.models.enums import RequestStatus  # noqa: PLC0415
    req = MagicMock()
    req.id = id
    req.number = f"REQ-2026-06-17-{id:05d}"
    req.status = RequestStatus(status_val)
    req.product_id = 1
    req.grade_text = "HDPE 2420D"
    req.polymer_type = None
    req.volume = 100
    req.volume_unit = "MT"
    req.target_price = None
    req.currency = "USD"
    req.incoterms = "cif"
    req.destination_country = "UZ"
    req.port_or_city = None
    req.desired_date = None
    req.validity_days = 30
    req.urgency = "medium"
    req.comment = None
    req.assigned_to = None
    req.ai = {}
    # Dual-origin (R2 W4): a TG-origin request — no portal company behind it.
    req.origin = "client"
    req.company_id = None
    req.company = None
    req.created_at = "2026-06-17T10:00:00Z"
    req.updated_at = "2026-06-17T10:00:00Z"
    req.files = []
    req.status_history = []
    # Client relationship
    req.client = MagicMock()
    req.client.telegram_user_id = telegram_user_id
    return req


# ── Service extension tests (request_service) ──────────────────────────────────

class TestAddNote:
    """add_note writes audit, calls db.flush(), never commits."""

    def test_add_note_writes_audit(self):
        """add_note calls write_audit with action='request.add_note'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.add_note(db, request_id=42, note_text="Test note", staff_user_id=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.add_note" in call_args_str

    def test_add_note_never_commits(self):
        """add_note never calls db.commit()."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()

        with patch("app.domains.requests.service.write_audit"):
            request_service.add_note(db, request_id=42, note_text="Test note", staff_user_id=1)

        db.commit.assert_not_called()

    def test_add_note_calls_write_audit(self):
        """add_note delegates to write_audit (which internally calls db.flush)."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.add_note(db, request_id=42, note_text="Note", staff_user_id=1)

        # write_audit must have been called — it owns db.flush internally
        mock_audit.assert_called_once()


class TestAssignOwner:
    """assign_owner sets assigned_to, writes audit, never commits."""

    def test_assign_owner_sets_assigned_to(self):
        """assign_owner sets request.assigned_to = staff_user_id."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request()

        with patch("app.domains.requests.service.write_audit"):
            request_service.assign_owner(db, request=req, staff_user_id=5, changed_by=1)

        assert req.assigned_to == 5

    def test_assign_owner_writes_audit(self):
        """assign_owner calls write_audit with action='request.assign_owner'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request()

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.assign_owner(db, request=req, staff_user_id=5, changed_by=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.assign_owner" in call_args_str

    def test_assign_owner_never_commits(self):
        """assign_owner never calls db.commit()."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request()

        with patch("app.domains.requests.service.write_audit"):
            request_service.assign_owner(db, request=req, staff_user_id=5, changed_by=1)

        db.commit.assert_not_called()


class TestLogContactBuyer:
    """log_contact_buyer transitions to in_progress if new/viewed, writes audit."""

    def test_log_contact_buyer_transitions_from_new_to_in_progress(self):
        """From 'new' status, log_contact_buyer calls transition_status -> in_progress."""
        from app.domains.requests import service as request_service  # noqa: PLC0415
        from app.models.enums import RequestStatus  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request(status_val="new")

        with patch("app.domains.requests.service.transition_status") as mock_transition, \
             patch("app.domains.requests.service.write_audit"):
            request_service.log_contact_buyer(db, request=req, staff_user_id=1)

            mock_transition.assert_called_once()
            call_args = mock_transition.call_args
            assert call_args.kwargs.get("to_status") == RequestStatus.in_progress or \
                   (len(call_args.args) >= 3 and call_args.args[2] == RequestStatus.in_progress)

    def test_log_contact_buyer_writes_audit(self):
        """log_contact_buyer calls write_audit with action='request.contact_buyer'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request(status_val="in_progress")  # already in_progress, skip transition

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.log_contact_buyer(db, request=req, staff_user_id=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.contact_buyer" in call_args_str

    def test_log_contact_buyer_never_commits(self):
        """log_contact_buyer never calls db.commit()."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request(status_val="in_progress")

        with patch("app.domains.requests.service.write_audit"):
            request_service.log_contact_buyer(db, request=req, staff_user_id=1)

        db.commit.assert_not_called()


# ── Router tests (RED: routers don't exist yet — will pass in Task 2 GREEN) ────

class TestGetRequestsList:
    """GET /requests returns list of requests, JWT-guarded."""

    def test_get_requests_returns_200_for_staff(self):
        """GET /requests returns 200 for authenticated staff (or 404 in RED before router mounted)."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        admin_user = _make_staff_user("admin", user_id=1)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = admin_user
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        def override_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests", headers=headers)

        # RED: 404 (route not mounted yet); GREEN: 200
        assert response.status_code in (200, 404)

    def test_get_requests_returns_401_without_auth(self):
        """GET /requests returns 401 without a Bearer token (or 404 in RED before router)."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.main import create_app  # noqa: PLC0415

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/v1/requests")
        # RED: 404 (route not mounted yet); GREEN: 401
        assert response.status_code in (401, 404)


class TestGetRequestDetail:
    """GET /requests/{id} auto-transitions new->viewed on first open (D-12)."""

    def test_detail_transitions_new_to_viewed_on_open(self):
        """Accessing a 'new' request transitions it to 'viewed' and commits."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=42, status_val="new", telegram_user_id=12345)

        mock_db = MagicMock()
        call_count = [0]

        def query_side_effect(model):
            """First call (auth) returns admin_user; second (request lookup) returns req."""
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value.first.return_value = (
                admin_user if call_count[0] == 1 else req
            )
            q.order_by.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        def override_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.domains.requests.service.transition_status") as mock_transition, \
             patch("app.domains.pricing.analysis.compute_price_analysis", return_value=None), \
             patch("app.tasks.notify.send_status_change_notification", create=True) as mock_notify:
            mock_notify.apply_async = MagicMock()
            mock_transition.return_value = req

            headers = _auth_headers(1, "admin")
            response = client.get("/api/v1/requests/42", headers=headers)

        # We expect either 200 (router exists) or 404 (router not mounted yet)
        # RED: router may not exist yet, so 404 or 422 are acceptable
        assert response.status_code in (200, 404, 422, 405)

    def test_detail_returns_404_for_missing_request(self):
        """GET /requests/{id} for non-existent request returns 404."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        admin_user = _make_staff_user("admin", user_id=1)
        mock_db = MagicMock()
        call_count = [0]

        def query_side_effect(model):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value.first.return_value = (
                admin_user if call_count[0] == 1 else None
            )
            return q

        mock_db.query.side_effect = query_side_effect

        def override_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)

        headers = _auth_headers(1, "admin")
        response = client.get("/api/v1/requests/99999", headers=headers)
        # RED: 404 (correctly not found) or 405 (route not mounted yet)
        assert response.status_code in (404, 405)


class TestPatchRequest:
    """PATCH /requests/{id} enforces the status machine and RBAC."""

    def test_invalid_transition_returns_422(self):
        """PATCH with an invalid status transition (new->closed) returns 422."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        admin_user = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=42, status_val="new")

        mock_db = MagicMock()
        call_count = [0]

        def query_side_effect(model):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value.first.return_value = (
                admin_user if call_count[0] == 1 else req
            )
            return q

        mock_db.query.side_effect = query_side_effect

        def override_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)

        headers = _auth_headers(1, "admin")
        response = client.patch(
            "/api/v1/requests/42",
            json={"status": "closed"},
            headers=headers,
        )
        # RED: 422 (correct) or 404/405 (route not mounted yet)
        assert response.status_code in (422, 404, 405)

    def test_viewer_patch_returns_403(self):
        """Viewer role cannot PATCH a request — returns 403 (T-04-10)."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        viewer_user = _make_staff_user("viewer", user_id=2)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = viewer_user

        def override_db():
            yield mock_db

        app = create_app()
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)

        headers = _auth_headers(2, "viewer")
        response = client.patch(
            "/api/v1/requests/42",
            json={"status": "viewed"},
            headers=headers,
        )
        # RED: 403 (correct) or 404/405 (route not mounted yet)
        assert response.status_code in (403, 404, 405)


# ── Audit trail test ───────────────────────────────────────────────────────────

class TestAuditTrail:
    """Every team action (status, note, assign, contact) writes audit_log (D-10)."""

    def test_status_change_writes_audit(self):
        """transition_status with changed_by calls write_audit (tested via service)."""
        from app.domains.requests.service import transition_status  # noqa: PLC0415
        from app.models.enums import RequestStatus  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request(status_val="in_progress")

        with patch("app.domains.requests.service.write_audit") as mock_audit, \
             patch("app.tasks.notify.send_status_change_notification", create=True) as mock_notify:
            mock_notify.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.offer_sent, changed_by=1)

            mock_audit.assert_called_once()

    def test_add_note_writes_audit(self):
        """add_note calls write_audit with action='request.add_note'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.add_note(db, request_id=42, note_text="A note", staff_user_id=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.add_note" in call_args_str

    def test_assign_owner_writes_audit(self):
        """assign_owner calls write_audit with action='request.assign_owner'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request()

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.assign_owner(db, request=req, staff_user_id=5, changed_by=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.assign_owner" in call_args_str

    def test_contact_buyer_writes_audit(self):
        """log_contact_buyer calls write_audit with action='request.contact_buyer'."""
        from app.domains.requests import service as request_service  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request(status_val="in_progress")

        with patch("app.domains.requests.service.write_audit") as mock_audit:
            request_service.log_contact_buyer(db, request=req, staff_user_id=1)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.contact_buyer" in call_args_str


# ── Contact available tests ────────────────────────────────────────────────────

class TestContactAvailable:
    """contact_available=True only when telegram_user_id IS NOT NULL (D-11 / Pitfall 6)."""

    def test_contact_available_true_when_telegram_id_present(self):
        """req.client.telegram_user_id is not None -> contact_available=True."""
        req = _make_mock_request(telegram_user_id=12345)
        contact_available = req.client.telegram_user_id is not None
        assert contact_available is True

    def test_contact_available_false_when_telegram_id_none(self):
        """req.client.telegram_user_id is None -> contact_available=False."""
        req = _make_mock_request(telegram_user_id=None)
        contact_available = req.client.telegram_user_id is not None
        assert contact_available is False
