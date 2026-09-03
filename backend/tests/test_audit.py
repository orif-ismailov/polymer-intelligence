"""
Tests for audit_service.write_audit and that POST /auth/login writes an audit row.

Covers:
- write_audit inserts exactly one audit_log row with correct fields
- A successful login writes an audit_log row with action='auth.login' and the user's id
- A failed login does NOT write an audit_log row (test_auth_login tests cover the 401 flow)
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_staff_user(id: int = 1, role: str = "admin", is_active: bool = True):
    from app.core.security import hash_password
    user = MagicMock()
    user.id = id
    user.email = "admin@polymer.uz"
    user.is_admin = role == "admin"
    user.is_active = is_active
    user.password_hash = hash_password("admin_password_secure")
    return user


def test_write_audit_calls_db_add_and_commit():
    """write_audit(db, ...) adds an AuditLog row and commits."""
    from app.services.audit_service import write_audit

    mock_db = MagicMock()
    write_audit(
        db=mock_db,
        staff_user_id=1,
        action="auth.login",
        entity="staff_users",
        entity_id="1",
        details={"ip": "127.0.0.1"},
    )

    # db.add should have been called once with an AuditLog instance
    assert mock_db.add.called, "write_audit should call db.add"
    assert mock_db.commit.called or mock_db.flush.called, (
        "write_audit should call db.commit or db.flush"
    )


def test_write_audit_creates_audit_log_instance():
    """write_audit creates an AuditLog model instance with correct fields."""
    from app.models.staff import AuditLog
    from app.services.audit_service import write_audit

    captured_instances = []

    mock_db = MagicMock()
    mock_db.add.side_effect = lambda obj: captured_instances.append(obj)

    write_audit(
        db=mock_db,
        staff_user_id=42,
        action="auth.login",
        entity="staff_users",
        entity_id="42",
        details={"source": "test"},
    )

    assert len(captured_instances) == 1
    instance = captured_instances[0]
    assert isinstance(instance, AuditLog)
    assert instance.staff_user_id == 42
    assert instance.action == "auth.login"
    assert instance.entity == "staff_users"
    assert instance.entity_id == "42"
    assert instance.details == {"source": "test"}


def test_login_writes_audit_log_row():
    """A successful POST /auth/login writes one audit_log row."""
    from app.core.db import get_db
    from app.main import create_app

    admin_user = _make_staff_user(id=1, role="admin", is_active=True)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    added_objects: list = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@polymer.uz", "password": "admin_password_secure"},
        )

    assert resp.status_code == 200, resp.text

    # Find AuditLog instance among added objects
    from app.models.staff import AuditLog

    audit_rows = [obj for obj in added_objects if isinstance(obj, AuditLog)]
    assert len(audit_rows) == 1, (
        f"Expected 1 audit_log row, got {len(audit_rows)}. Added objects: {added_objects}"
    )

    audit_row = audit_rows[0]
    assert audit_row.action == "auth.login"
    assert audit_row.staff_user_id == 1


def test_failed_login_does_not_write_audit_log():
    """A failed login (wrong password) does NOT write an audit_log row."""
    from app.core.db import get_db
    from app.main import create_app
    from app.models.staff import AuditLog

    admin_user = _make_staff_user(id=1, role="admin", is_active=True)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    added_objects: list = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@polymer.uz", "password": "wrong_password"},
        )

    assert resp.status_code == 401

    audit_rows = [obj for obj in added_objects if isinstance(obj, AuditLog)]
    assert len(audit_rows) == 0, (
        f"Failed login should NOT write audit_log, but got: {audit_rows}"
    )
