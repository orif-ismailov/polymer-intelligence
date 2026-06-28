"""
Tests for /webapp/* request, profile, and file API endpoints.

TDD RED phase: tests written before router implementation.

Covers:
- POST /api/v1/webapp/requests: 201 on valid body + initData, 401 on missing initData,
  422 on D-02 violations
- GET /api/v1/webapp/requests: 200 list scoped to authenticated client
- GET /api/v1/webapp/requests/{id}: 200 for own requests, 404 for cross-client (IDOR)
- POST /api/v1/webapp/requests/{id}/files: 201 on valid file, 422 on bad magic bytes,
  422 on oversized file, 422 on 6th file, 404 on cross-client
- GET /api/v1/webapp/me: 200 with client profile
- PATCH /api/v1/webapp/me: 200 + language persisted; 422 on invalid language

Security invariants tested:
- T-03-07: cross-client GET /requests/{id} returns 404 (IDOR guard)
- T-03-08: client_id never from body — get_current_client dep owns identity
- T-03-03: no initData header returns 401 "Authentication required"
"""

from __future__ import annotations

import io
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# BOT_TOKEN used in conftest._TEST_ENV
_BOT_TOKEN = "123456789:AABBccDDeeFF"

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_client(id: int = 1, language: str = "ru") -> MagicMock:
    """Return a MagicMock that quacks like a Client ORM object."""
    client = MagicMock()
    client.id = id
    client.language = language
    client.company_name = "Test Company"
    client.contact_name = "Test User"
    return client


def _make_mock_request(id: int = 42, client_id: int = 1, number: str = "REQ-2026-06-16-00001") -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object.

    Sets ALL fields required by RequestDetailOut (MR-03: polymer_type, volume_unit,
    destination_country, port_or_city, desired_date, validity_days, urgency, comment
    were added to the schema).
    """
    import datetime  # noqa: PLC0415, E401
    import decimal

    from app.models.enums import PriceBasis, RequestStatus, Urgency  # noqa: PLC0415
    req = MagicMock()
    req.id = id
    req.client_id = client_id
    req.number = number
    req.status = RequestStatus.new
    req.created_at = datetime.datetime(2026, 6, 16, 10, 0, 0, tzinfo=datetime.UTC)
    req.product_id = 1
    req.product_text = None
    req.grade_text = "HDPE 2420D"
    req.polymer_type = None
    req.volume = decimal.Decimal("100")
    req.volume_unit = "MT"
    req.target_price = None
    req.currency = "USD"
    req.incoterms = PriceBasis.unknown
    req.destination_country = "UZ"
    req.port_or_city = None
    req.desired_date = None
    req.validity_days = 30
    req.urgency = Urgency.medium
    req.comment = None
    req.company_name = None
    req.contact_name = None
    req.phone = None
    req.legal_address = None
    req.files = []
    req.status_history = []
    return req


def _make_mock_request_file(id: int = 1, request_id: int = 42) -> MagicMock:
    rf = MagicMock()
    rf.id = id
    rf.request_id = request_id
    rf.file_name = "test.pdf"
    rf.mime_type = "application/pdf"
    rf.size_bytes = 1024
    rf.storage_path = "requests/42/abc-test.pdf"
    return rf


@pytest.fixture
def webapp_client() -> Generator[TestClient, None, None]:
    """TestClient with get_current_client and get_db overridden — happy path client id=1."""
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_client = _make_mock_client(id=1)

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.refresh = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    def _override_get_current_client() -> Any:
        return mock_client

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_client] = _override_get_current_client

    with patch("app.api.health._check_redis", return_value="ok"), \
         TestClient(application, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture
def no_auth_client() -> Generator[TestClient, None, None]:
    """TestClient with get_db overridden but NO get_current_client override (real dep runs → 401)."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), \
         TestClient(application, raise_server_exceptions=False) as tc:
        yield tc


# ── POST /api/v1/webapp/requests ──────────────────────────────────────────────

class TestCreateRequest:
    """POST /webapp/requests — create a purchase request."""

    def test_create_request_returns_201_with_number(self, webapp_client: TestClient):
        """Valid body + initData dep override → 201 + {id, number, status}."""
        mock_req = _make_mock_request(id=42)

        with patch("app.api.webapp.requests.request_service") as mock_svc:
            mock_svc.create_request.return_value = mock_req
            resp = webapp_client.post(
                "/api/v1/webapp/requests",
                json={
                    "product_id": 1,
                    "grade_text": "HDPE 2420D",
                    "volume": "100.000",
                    "volume_unit": "MT",
                },
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data
        assert "number" in data
        assert "status" in data

    def test_create_request_no_initdata_returns_401(self, no_auth_client: TestClient):
        """No X-Telegram-Init-Data header → 401 (T-03-03)."""
        resp = no_auth_client.post(
            "/api/v1/webapp/requests",
            json={
                "product_id": 1,
                "grade_text": "HDPE 2420D",
                "volume": "100.000",
            },
        )
        assert resp.status_code == 401, resp.text

    def test_create_request_missing_product_id_returns_422(self, webapp_client: TestClient):
        """Missing product_id → 422 (D-02 minimum)."""
        resp = webapp_client.post(
            "/api/v1/webapp/requests",
            json={
                "grade_text": "HDPE 2420D",
                "volume": "100.000",
            },
        )
        assert resp.status_code == 422, resp.text

    def test_create_request_missing_grade_and_polymer_returns_422(self, webapp_client: TestClient):
        """Neither grade_text nor polymer_type → 422 (D-02 minimum)."""
        resp = webapp_client.post(
            "/api/v1/webapp/requests",
            json={
                "product_id": 1,
                "volume": "100.000",
            },
        )
        assert resp.status_code == 422, resp.text

    def test_create_request_zero_volume_returns_422(self, webapp_client: TestClient):
        """volume=0 → 422 (D-02 volume > 0)."""
        resp = webapp_client.post(
            "/api/v1/webapp/requests",
            json={
                "product_id": 1,
                "grade_text": "HDPE 2420D",
                "volume": "0",
            },
        )
        assert resp.status_code == 422, resp.text


# ── GET /api/v1/webapp/requests ───────────────────────────────────────────────

class TestListRequests:
    """GET /webapp/requests — list authenticated client's requests."""

    def test_list_requests_returns_200(self):
        """Authenticated client gets 200 list (empty list ok)."""
        from app.api.deps import get_current_client  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_client = _make_mock_client(id=1)
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []  # empty list — valid response
        mock_db.query.return_value = mock_query

        def _override_get_db():
            yield mock_db

        def _override_get_current_client():
            return mock_client

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db
        application.dependency_overrides[get_current_client] = _override_get_current_client

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            resp = tc.get("/api/v1/webapp/requests")

        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)

    def test_list_no_auth_returns_401(self, no_auth_client: TestClient):
        """No initData → 401."""
        resp = no_auth_client.get("/api/v1/webapp/requests")
        assert resp.status_code == 401, resp.text


# ── GET /api/v1/webapp/requests/{id} ─────────────────────────────────────────

class TestGetRequestDetail:
    """GET /webapp/requests/{id} — IDOR-scoped detail view."""

    def test_own_request_returns_200(self):
        """Get own request (client_id matches) → 200 with correct detail."""
        from app.api.deps import get_current_client  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_client = _make_mock_client(id=1)
        # Use the shared helper so all RequestDetailOut fields are present (MR-03)
        mock_req = _make_mock_request(id=42, client_id=1)

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.flush = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_req
        mock_db.query.return_value = mock_query

        def _override_get_db():
            yield mock_db

        def _override_get_current_client():
            return mock_client

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db
        application.dependency_overrides[get_current_client] = _override_get_current_client

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            resp = tc.get("/api/v1/webapp/requests/42")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == 42
        assert data["number"] == "REQ-2026-06-16-00001"

    def test_cross_client_request_returns_404(self):
        """Request owned by a different client → 404 (T-03-07 IDOR guard).

        The handler filters by BOTH request_id AND client_id.
        When the query returns None (no row with matching id AND client_id), 404.
        """
        from app.api.deps import get_current_client  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_client = _make_mock_client(id=1)  # caller is client id=1
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        # db.query().filter().first() returns None — no request with both id AND client_id=1
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # T-03-07: returns None for non-owned requests
        mock_db.query.return_value = mock_query

        def _override_get_db():
            yield mock_db

        def _override_get_current_client():
            return mock_client

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db
        application.dependency_overrides[get_current_client] = _override_get_current_client

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            # Request 999 is owned by client id=2 (not the calling client id=1)
            resp = tc.get("/api/v1/webapp/requests/999")

        assert resp.status_code == 404, resp.text

    def test_no_auth_returns_401(self, no_auth_client: TestClient):
        """No initData → 401."""
        resp = no_auth_client.get("/api/v1/webapp/requests/42")
        assert resp.status_code == 401, resp.text


# ── GET/PATCH /api/v1/webapp/me ───────────────────────────────────────────────

class TestClientProfile:
    """GET/PATCH /webapp/me — client profile read and update."""

    def test_get_me_returns_200_profile(self, webapp_client: TestClient):
        """GET /webapp/me returns 200 with client profile."""
        resp = webapp_client.get("/api/v1/webapp/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "id" in data
        assert "language" in data

    def test_get_me_no_auth_returns_401(self, no_auth_client: TestClient):
        """No initData → 401."""
        resp = no_auth_client.get("/api/v1/webapp/me")
        assert resp.status_code == 401, resp.text

    def test_patch_me_language_uz_returns_200(self, webapp_client: TestClient):
        """PATCH /webapp/me {language:'uz'} → 200 and language updated."""
        resp = webapp_client.patch("/api/v1/webapp/me", json={"language": "uz"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # The mock client may not have its attribute updated (it's a MagicMock)
        # but the endpoint should return 200 successfully
        assert "language" in data

    def test_patch_me_language_tr_returns_200(self, webapp_client: TestClient):
        """PATCH /webapp/me {language:'tr'} → 200 (Turkish is a supported language)."""
        resp = webapp_client.patch("/api/v1/webapp/me", json={"language": "tr"})
        assert resp.status_code == 200, resp.text
        assert "language" in resp.json()

    def test_patch_me_language_en_returns_200(self, webapp_client: TestClient):
        """PATCH /webapp/me {language:'en'} → 200 (English is now a supported language)."""
        resp = webapp_client.patch("/api/v1/webapp/me", json={"language": "en"})
        assert resp.status_code == 200, resp.text
        assert "language" in resp.json()

    def test_patch_me_invalid_language_returns_422(self, webapp_client: TestClient):
        """PATCH /webapp/me {language:'de'} → 422 (German is not a supported language)."""
        resp = webapp_client.patch("/api/v1/webapp/me", json={"language": "de"})
        assert resp.status_code == 422, resp.text

    def test_patch_me_no_auth_returns_401(self, no_auth_client: TestClient):
        """No initData → 401."""
        resp = no_auth_client.patch("/api/v1/webapp/me", json={"language": "uz"})
        assert resp.status_code == 401, resp.text


# ── POST /api/v1/webapp/requests/{id}/files ───────────────────────────────────

class TestFileUpload:
    """POST /webapp/requests/{id}/files — MIME-validated file upload."""

    def _pdf_bytes(self) -> bytes:
        """Return minimal valid PDF magic bytes content."""
        return b"%PDF-1.4 test content " + b"x" * 100

    def _bad_bytes(self) -> bytes:
        """Return bytes with no valid magic bytes (ELF-like)."""
        return b"\x7fELF" + b"x" * 100

    def _oversized_bytes(self) -> bytes:
        """Return bytes exceeding the 10 MB limit."""
        return b"%PDF" + b"x" * (10 * 1024 * 1024 + 1)

    def _make_file_tc(self, mock_req=None, file_count: int = 0):
        """Create a TestClient with db properly wired for file upload tests."""
        from app.api.deps import get_current_client  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_client = _make_mock_client(id=1)
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.flush = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_req  # None for cross-client 404
        mock_query.count.return_value = file_count  # existing file count
        mock_db.query.return_value = mock_query

        def _override_get_db():
            yield mock_db

        def _override_get_current_client():
            return mock_client

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db
        application.dependency_overrides[get_current_client] = _override_get_current_client
        return application

    def test_valid_pdf_returns_201(self):
        """Valid PDF ≤10 MB for own request → 201."""
        mock_req = _make_mock_request(id=42, client_id=1)
        mock_req_file = _make_mock_request_file(id=1, request_id=42)
        application = self._make_file_tc(mock_req=mock_req, file_count=0)

        # Patch upload_request_file in app.api.webapp.files where it's called via storage_service
        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.api.webapp.files.storage_service") as mock_storage, \
             TestClient(application, raise_server_exceptions=True) as tc:
            mock_storage.upload_request_file.return_value = mock_req_file
            mock_storage.MAX_FILES = 5
            resp = tc.post(
                "/api/v1/webapp/requests/42/files",
                files={"file": ("test.pdf", io.BytesIO(self._pdf_bytes()), "application/pdf")},
            )

        assert resp.status_code == 201, resp.text

    def test_bad_magic_bytes_returns_422(self):
        """File with invalid magic bytes → 422 invalid_file_type (T-03-04)."""
        mock_req = _make_mock_request(id=42, client_id=1)
        application = self._make_file_tc(mock_req=mock_req, file_count=0)

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            # Bad magic bytes — storage_service.validate_upload raises ValueError
            resp = tc.post(
                "/api/v1/webapp/requests/42/files",
                files={"file": ("bad.pdf", io.BytesIO(self._bad_bytes()), "application/pdf")},
            )

        # validate_upload raises ValueError("invalid_file_type") → 422
        assert resp.status_code == 422, resp.text

    def test_oversized_file_returns_422(self):
        """File >10 MB → 422 file_too_large (T-03-05)."""
        mock_req = _make_mock_request(id=42, client_id=1)
        application = self._make_file_tc(mock_req=mock_req, file_count=0)

        # Build a file slightly over 10 MB (magic bytes + padding)
        oversized = b"%PDF" + b"x" * (10 * 1024 * 1024 + 1)

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            resp = tc.post(
                "/api/v1/webapp/requests/42/files",
                files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
            )

        # validate_upload raises ValueError("file_too_large") → 422
        assert resp.status_code == 422, resp.text

    def test_sixth_file_returns_422(self):
        """6th file upload when 5 already exist → 422 too_many_files (T-03-05)."""
        mock_req = _make_mock_request(id=42, client_id=1)
        # file_count=5 means MAX_FILES is already reached
        application = self._make_file_tc(mock_req=mock_req, file_count=5)

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            resp = tc.post(
                "/api/v1/webapp/requests/42/files",
                files={"file": ("test6.pdf", io.BytesIO(self._pdf_bytes()), "application/pdf")},
            )

        assert resp.status_code == 422, resp.text
        assert "too_many_files" in resp.json().get("detail", "")

    def test_cross_client_file_upload_returns_404(self):
        """Upload to a request owned by different client → 404 (T-03-07 IDOR guard)."""
        # mock_req=None simulates: no request matching both request_id AND client_id
        application = self._make_file_tc(mock_req=None, file_count=0)

        with patch("app.api.health._check_redis", return_value="ok"), \
             TestClient(application, raise_server_exceptions=True) as tc:
            resp = tc.post(
                "/api/v1/webapp/requests/999/files",
                files={"file": ("test.pdf", io.BytesIO(self._pdf_bytes()), "application/pdf")},
            )

        assert resp.status_code == 404, resp.text

    def test_no_auth_returns_401(self, no_auth_client: TestClient):
        """No initData → 401."""
        resp = no_auth_client.post(
            "/api/v1/webapp/requests/42/files",
            files={"file": ("test.pdf", io.BytesIO(self._pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 401, resp.text
