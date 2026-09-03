"""
Tests for POST /api/v1/auth/login and POST /api/v1/auth/refresh.

Covers:
- Correct credentials → 200 + access_token body + httpOnly refresh cookie
- Wrong password → 401, no Set-Cookie
- Inactive user → 401
- POST /auth/refresh with valid cookie → new access token
- POST /auth/refresh without cookie → 401
- POST /auth/refresh with invalid cookie value → 401
- Identity comes from verified JWT, never from request body
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Test fixtures ──────────────────────────────────────────────────────────────

def _make_staff_user(
    id: int = 1,
    email: str = "admin@polymer.uz",
    role: str = "admin",
    is_active: bool = True,
    password: str = "admin_password_secure",
):
    """Create a mock StaffUser ORM object."""
    from app.core.security import hash_password
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = role == "admin"
    user.is_active = is_active
    user.password_hash = hash_password(password)
    return user


@pytest.fixture
def auth_client(monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient with a mocked DB that has one seeded admin user."""
    from app.core.db import get_db
    from app.main import create_app

    admin_user = _make_staff_user(
        id=1,
        email="admin@polymer.uz",
        role="admin",
        is_active=True,
        password="admin_password_secure",
    )

    # Mock DB session that can look up users
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = admin_user
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query

    # Also mock the add/commit/flush for audit_log writes
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.refresh = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture
def inactive_auth_client(monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient where the only user is inactive."""
    from app.core.db import get_db
    from app.main import create_app

    inactive_user = _make_staff_user(
        id=2,
        email="inactive@polymer.uz",
        role="viewer",
        is_active=False,
        password="viewer_password",
    )

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = inactive_user
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture
def no_user_auth_client() -> Generator[TestClient, None, None]:
    """TestClient where email lookup returns None (user not found)."""
    from app.core.db import get_db
    from app.main import create_app

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = None
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as tc:
        yield tc


# ── Login tests ────────────────────────────────────────────────────────────────

def test_login_success_returns_access_token(auth_client: TestClient):
    """Correct credentials return 200 with access_token in the body."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["is_admin"] is True


def test_login_success_sets_httponly_refresh_cookie(auth_client: TestClient):
    """Successful login sets an httpOnly refresh cookie."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert resp.status_code == 200, resp.text

    # Confirm a Set-Cookie header is present
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie_header or "HttpOnly" in set_cookie_header, (
        f"Expected HttpOnly refresh cookie but got: {set_cookie_header}"
    )
    # Check the cookie has HttpOnly attribute
    cookie_lower = set_cookie_header.lower()
    assert "httponly" in cookie_lower, f"Refresh cookie should be HttpOnly: {set_cookie_header}"


def test_login_success_cookie_is_samesite(auth_client: TestClient):
    """Refresh cookie has SameSite attribute set."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert resp.status_code == 200
    set_cookie_header = resp.headers.get("set-cookie", "").lower()
    assert "samesite" in set_cookie_header, (
        f"Refresh cookie should have SameSite attribute: {set_cookie_header}"
    )


def test_login_wrong_password_returns_401(auth_client: TestClient):
    """Wrong password returns 401 with no Set-Cookie."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "wrong_password"},
    )
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers


def test_login_wrong_email_returns_401(no_user_auth_client: TestClient):
    """Non-existent email returns 401 (no user enumeration)."""
    resp = no_user_auth_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@polymer.uz", "password": "any_password"},
    )
    assert resp.status_code == 401
    # Must NOT reveal which field was wrong
    body = resp.json()
    detail = body.get("detail", "").lower()
    assert "email" not in detail or "password" not in detail, (
        "Login failure should not hint at which field was wrong"
    )


def test_login_inactive_user_returns_401(inactive_auth_client: TestClient):
    """An inactive user cannot log in."""
    resp = inactive_auth_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@polymer.uz", "password": "viewer_password"},
    )
    assert resp.status_code in (401, 403)


# ── Refresh tests ──────────────────────────────────────────────────────────────

def test_refresh_with_valid_cookie_returns_new_access_token(auth_client: TestClient):
    """POST /auth/refresh with valid cookie returns a new access token."""
    # First login to get the cookie
    login_resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert login_resp.status_code == 200

    # The TestClient should carry the cookie automatically
    refresh_resp = auth_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data


def test_refresh_without_cookie_returns_401(auth_client: TestClient):
    """POST /auth/refresh without a cookie returns 401."""
    # Use a fresh client with no cookies
    from app.core.db import get_db
    from app.main import create_app

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = _make_staff_user()
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query

    def _override_get_db():
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as fresh_client:
        # Don't set any cookies - call refresh directly
        resp = fresh_client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


def test_refresh_with_invalid_cookie_returns_401(auth_client: TestClient):
    """POST /auth/refresh with an invalid cookie value returns 401."""
    from fastapi.testclient import TestClient as TestClientAlias  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = _make_staff_user()
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query

    def _override_get_db():
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClientAlias(application, raise_server_exceptions=True) as bad_client:
        bad_client.cookies.set("refresh_token", "totally.invalid.token")
        resp = bad_client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


# ── Logout tests (QA 2026-07-28 #3) ───────────────────────────────────────────


def test_logout_clears_the_refresh_cookie(auth_client: TestClient):
    """The cookie IS the session — logout must revoke it, not just drop the token."""
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert login.status_code == 200
    assert auth_client.cookies.get("refresh_token")

    resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204, resp.text
    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    # An expiry in the past is how a cookie is deleted.
    assert "expires=" in set_cookie.lower() or "max-age=0" in set_cookie.lower()

    # And the browser really cannot re-authenticate afterwards.
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_audits_the_identity_from_the_cookie(auth_client: TestClient):
    """Identity comes from the verified `sub` claim, never the request (T-03-06)."""
    auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    with patch("app.api.auth.write_audit") as mock_audit:
        assert auth_client.post("/api/v1/auth/logout").status_code == 204

    _, kwargs = mock_audit.call_args
    assert kwargs["action"] == "auth.logout"
    assert kwargs["staff_user_id"] == 1


def test_logout_without_a_cookie_is_still_204(auth_client: TestClient):
    """Logout is idempotent — it must never leave a caller believing they are signed in."""
    with patch("app.api.auth.write_audit") as mock_audit:
        resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204, resp.text
    mock_audit.assert_not_called()


def test_logout_with_an_unreadable_cookie_still_clears_it(auth_client: TestClient):
    """A garbage/expired cookie must not be the reason you are stuck signed in."""
    auth_client.cookies.set("refresh_token", "totally.invalid.token")
    with patch("app.api.auth.write_audit") as mock_audit:
        resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204, resp.text
    assert "refresh_token=" in resp.headers.get("set-cookie", "")
    mock_audit.assert_not_called()  # unattributable, but still revoked


def test_logout_needs_no_access_token(auth_client: TestClient):
    """Deliberately unauthenticated: an expired access token must not block logout."""
    auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    resp = auth_client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer expired.garbage.token"}
    )
    assert resp.status_code == 204, resp.text


# ── Security hardening tests (CR-04, CR-05, T-03-01) ──────────────────────────

def test_dummy_verify_does_not_raise() -> None:
    """dummy_verify with any password must not raise (performs argon2 work against a real hash).

    CR-05: the unknown-user path must perform full argon2 KDF so timings converge.
    A valid argon2 hash is pre-computed at import; verify swallows the mismatch.
    """
    from app.core.security import dummy_verify
    # Must not raise on any plaintext input
    dummy_verify("any_password_at_all")
    dummy_verify("")
    dummy_verify("a" * 100)


def test_dummy_verify_does_not_raise_invalid_hash_error() -> None:
    """dummy_verify must NOT raise InvalidHashError — confirms it uses a real precomputed hash.

    T-03-01: the old implementation raised InvalidHashError immediately (no KDF work done).
    """
    from argon2.exceptions import InvalidHashError

    from app.core.security import dummy_verify
    try:
        dummy_verify("probe_password")
    except InvalidHashError as exc:
        raise AssertionError(
            "dummy_verify raised InvalidHashError — the dummy hash is malformed "
            "(not a real argon2 hash). CR-05: replace with _hasher.hash() precomputed at import."
        ) from exc


def test_unknown_user_path_calls_dummy_verify(no_user_auth_client: TestClient) -> None:
    """authenticate() with a non-existent email must call dummy_verify (user-not-found branch).

    CR-05 / T-03-01: verifies the timing-attack mitigation is actually wired in auth_service.py.
    """
    with patch("app.services.auth_service.dummy_verify") as mock_dv:
        resp = no_user_auth_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@polymer.uz", "password": "any_password"},
        )
    assert resp.status_code == 401
    mock_dv.assert_called_once()


def test_valid_login_still_works_regression(auth_client: TestClient) -> None:
    """Regression: authenticate() still returns the StaffUser for valid credentials."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_wrong_password_returns_401_regression(auth_client: TestClient) -> None:
    """Regression: authenticate() returns None (401) for a wrong password."""
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@polymer.uz", "password": "totally_wrong_password"},
    )
    assert resp.status_code == 401
