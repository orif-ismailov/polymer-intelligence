"""
Tests for require_role / require_admin RBAC dependency.

Covers:
- require_role(admin): viewer token → 403, admin token → 200
- require_role(analyst, admin): analyst and admin → 200; trader and viewer → 403
- require_admin convenience alias: only admin passes
- Identity comes from verified JWT, not from request body (T-03-06)
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

def _make_staff_user(
    id: int,
    role: str,
    is_active: bool = True,
    email: str = "user@polymer.uz",
):
    """Create a mock StaffUser with the given role."""
    from app.core.security import hash_password
    from app.models.enums import StaffRole

    user = MagicMock()
    user.id = id
    user.email = email
    user.role = StaffRole(role)
    user.is_active = is_active
    user.password_hash = hash_password("any_password")
    return user


def _make_rbac_client(staff_user: MagicMock) -> TestClient:
    """Build a TestClient with get_db mocked to return the given staff_user."""
    from app.main import create_app
    from app.core.db import get_db

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    return TestClient(application, raise_server_exceptions=True)


def _auth_headers(staff_user_id: int, role: str) -> dict[str, str]:
    """Create a Bearer Authorization header with a valid access token."""
    from app.core.security import create_access_token

    token = create_access_token(subject=str(staff_user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


# ── require_admin tests ────────────────────────────────────────────────────────

def test_admin_route_allows_admin_token():
    """Admin-only route returns 200 for an admin token."""
    user = _make_staff_user(id=1, role="admin")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami", headers=_auth_headers(1, "admin"))
    assert resp.status_code == 200


def test_admin_route_rejects_viewer_token():
    """Admin-only route returns 403 for a viewer token (REQ-roles)."""
    user = _make_staff_user(id=4, role="viewer")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami", headers=_auth_headers(4, "viewer"))
    assert resp.status_code == 403


def test_admin_route_rejects_trader_token():
    """Admin-only route returns 403 for a trader token."""
    user = _make_staff_user(id=3, role="trader")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami", headers=_auth_headers(3, "trader"))
    assert resp.status_code == 403


def test_admin_route_rejects_analyst_token():
    """Admin-only route returns 403 for an analyst token."""
    user = _make_staff_user(id=2, role="analyst")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami", headers=_auth_headers(2, "analyst"))
    assert resp.status_code == 403


# ── require_role multi-role tests ──────────────────────────────────────────────

def test_analyst_admin_route_allows_analyst():
    """require_role(analyst, admin) route allows analyst token."""
    user = _make_staff_user(id=2, role="analyst")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/analyst/whoami", headers=_auth_headers(2, "analyst"))
    assert resp.status_code == 200


def test_analyst_admin_route_allows_admin():
    """require_role(analyst, admin) route allows admin token."""
    user = _make_staff_user(id=1, role="admin")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/analyst/whoami", headers=_auth_headers(1, "admin"))
    assert resp.status_code == 200


def test_analyst_admin_route_rejects_trader():
    """require_role(analyst, admin) route rejects trader token."""
    user = _make_staff_user(id=3, role="trader")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/analyst/whoami", headers=_auth_headers(3, "trader"))
    assert resp.status_code == 403


def test_analyst_admin_route_rejects_viewer():
    """require_role(analyst, admin) route rejects viewer token."""
    user = _make_staff_user(id=4, role="viewer")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/analyst/whoami", headers=_auth_headers(4, "viewer"))
    assert resp.status_code == 403


# ── Missing / invalid token tests ─────────────────────────────────────────────

def test_admin_route_rejects_no_token():
    """Admin-only route returns 401 when no Authorization header is provided."""
    user = _make_staff_user(id=1, role="admin")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami")
    assert resp.status_code == 401


def test_admin_route_rejects_malformed_token():
    """Admin-only route returns 401 for a malformed Bearer token."""
    user = _make_staff_user(id=1, role="admin")
    client = _make_rbac_client(user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/whoami",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
    assert resp.status_code == 401


def test_inactive_user_rejected_by_guard():
    """An inactive user's valid token is still rejected by the guard."""
    inactive_user = _make_staff_user(id=1, role="admin", is_active=False)
    client = _make_rbac_client(inactive_user)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/whoami", headers=_auth_headers(1, "admin"))
    # Should be 401 or 403 (inactive account)
    assert resp.status_code in (401, 403)
