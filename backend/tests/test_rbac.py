"""
Tests for the require_admin guard.

Staff authorization is a single question — is this account an administrator.
The four-role `staff_role` enum this replaced (migration 0042) could only be
changed with SQL, because nothing but the seeder ever wrote it.

Covers:
- require_admin: administrator → 200, non-administrator → 403
- authenticating is not the same as being authorized (a valid non-admin token is
  refused, not admitted)
- the decision is read from the staff ROW, not from the token (T-03-06)
- missing / malformed token → 401, inactive account → 403

These drive a real admin-gated route (`GET /admin/users`) rather than a demo
route built to be tested. A guard proven only against a hook that exists for the
test can pass while the endpoints people actually reach are ungated.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

#: A real administrator-only route. Its handler runs raw SQL, which the mocked
#: session below answers with an empty result set.
_ADMIN_ROUTE = "/api/v1/admin/users"


def _make_staff_user(
    id: int,
    is_admin: bool,
    is_active: bool = True,
    email: str = "user@polymer.uz",
):
    """Create a mock StaffUser."""
    from app.core.security import hash_password

    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active
    user.password_hash = hash_password("any_password")
    return user


def _make_rbac_client(staff_user: MagicMock) -> TestClient:
    """Build a TestClient with get_db mocked to return the given staff_user."""
    from app.core.db import get_db
    from app.main import create_app

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user
    # The route's own SELECT — empty, so the test turns on the guard alone.
    mock_db.execute.return_value.fetchall.return_value = []

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    return TestClient(application, raise_server_exceptions=True)


def _auth_headers(staff_user_id: int) -> dict[str, str]:
    """Create a Bearer Authorization header with a valid access token."""
    from app.core.security import create_access_token

    token = create_access_token(subject=str(staff_user_id))
    return {"Authorization": f"Bearer {token}"}


# ── require_admin ─────────────────────────────────────────────────────────────


def test_admin_route_allows_administrator():
    """An administrator reaches an admin-only route."""
    client = _make_rbac_client(_make_staff_user(id=1, is_admin=True))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(_ADMIN_ROUTE, headers=_auth_headers(1))
    assert resp.status_code == 200, resp.text


def test_admin_route_rejects_non_administrator():
    """A valid, active staff token that is not an administrator gets 403.

    Authenticating and being authorized are different questions: this account
    exists and its token verifies, and it is still refused.
    """
    client = _make_rbac_client(_make_staff_user(id=2, is_admin=False))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(_ADMIN_ROUTE, headers=_auth_headers(2))
    assert resp.status_code == 403
    assert "administrator" in resp.json()["detail"].lower()


def test_authorization_is_read_from_the_row_not_the_token():
    """Revoking admin takes effect on the next request, not on token expiry.

    The token is minted while the account is an administrator and is still
    perfectly valid; the row says otherwise by the time the request lands, and
    the row is what counts (T-03-06).
    """
    headers = _auth_headers(3)  # minted first — the token never changes
    client = _make_rbac_client(_make_staff_user(id=3, is_admin=False))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(_ADMIN_ROUTE, headers=headers)
    assert resp.status_code == 403


# ── Missing / invalid token ───────────────────────────────────────────────────


def test_admin_route_rejects_no_token():
    """Admin-only route returns 401 when no Authorization header is provided."""
    client = _make_rbac_client(_make_staff_user(id=1, is_admin=True))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(_ADMIN_ROUTE)
    assert resp.status_code == 401


def test_admin_route_rejects_malformed_token():
    """Admin-only route returns 401 for a malformed Bearer token."""
    client = _make_rbac_client(_make_staff_user(id=1, is_admin=True))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            _ADMIN_ROUTE,
            headers={"Authorization": "Bearer not.a.real.token"},
        )
    assert resp.status_code == 401


def test_inactive_administrator_rejected_by_guard():
    """A deactivated administrator's valid token is still rejected.

    This is what makes `is_active` a real off switch: deactivating someone does
    not wait for their 15-minute token to expire.
    """
    inactive = _make_staff_user(id=1, is_admin=True, is_active=False)
    client = _make_rbac_client(inactive)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(_ADMIN_ROUTE, headers=_auth_headers(1))
    assert resp.status_code == 403
