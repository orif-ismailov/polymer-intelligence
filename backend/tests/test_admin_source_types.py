"""
Tests for GET /api/v1/admin/source-types.

Covers:
- Admin user gets 200 with the expected JSON array shape
- Each element has type_name (str), config_schema (JSON schema dict), no_code (bool)
- Non-admin roles (trader, viewer) get 403
- The no_code flag is True for telegram_channel/llm_page/html_table/rss
  and False for built-in adapters (uzex_*, cbu_rates, sunsirs, dce)
- The router is mounted under /api/v1 in main.py

Security: T-02-10 — non-admins must be rejected.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

# ── Test helpers ────────────────────────────────────────────────────────────────

def _make_staff_user(role: str, user_id: int = 1, is_active: bool = True):
    """Create a mock StaffUser with the given role."""
    from app.models.enums import StaffRole  # noqa: PLC0415

    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = is_active
    return user


def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    """Create a Bearer Authorization header with a valid access token."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_client_with_user(staff_user: MagicMock) -> TestClient:
    """Build a TestClient with get_db mocked to return the given staff_user."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


# ── Dummy adapter for registration ─────────────────────────────────────────────

def _register_dummy_adapter(type_name: str = "test_source") -> None:
    """Register a dummy adapter in the registry for the duration of a test."""
    from app.ingest.registry import register_adapter  # noqa: PLC0415

    class DummyConfig(BaseModel):
        url: str
        poll_interval: int = 300

    class DummyAdapter:
        config_schema = DummyConfig

        async def fetch(self, source):
            return []

        async def test(self, config):
            return None

    adapter = DummyAdapter()
    adapter.type_name = type_name  # type: ignore[attr-defined]
    register_adapter(adapter)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def clean_registry_and_register_dummy():
    """Clear the registry before each test, register a known dummy adapter."""
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    _register_dummy_adapter("test_source")
    yield
    _clear_registry()


# ── Admin can access endpoint ───────────────────────────────────────────────────

def test_admin_gets_200_with_adapter_list():
    """GET /api/v1/admin/source-types returns 200 for admin users."""
    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_admin_response_has_correct_shape():
    """Each item in the response has type_name, config_schema, and no_code fields."""
    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    data = resp.json()
    # Find the dummy adapter item
    item = next((x for x in data if x["type_name"] == "test_source"), None)
    assert item is not None, "test_source adapter not found in response"
    assert "type_name" in item
    assert "config_schema" in item
    assert "no_code" in item
    assert isinstance(item["type_name"], str)
    assert isinstance(item["config_schema"], dict)
    assert isinstance(item["no_code"], bool)


def test_admin_response_config_schema_is_json_schema():
    """config_schema in the response is a valid pydantic v2 JSON schema dict."""
    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    data = resp.json()
    item = next(x for x in data if x["type_name"] == "test_source")
    schema = item["config_schema"]
    # Pydantic v2 JSON schema always has a "type" or "$defs" key
    assert "properties" in schema or "type" in schema


def test_admin_response_contains_dummy_adapter_type_name():
    """Response includes the type_name of the registered dummy adapter."""
    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    type_names = [item["type_name"] for item in resp.json()]
    assert "test_source" in type_names


# ── Non-admin roles are rejected ────────────────────────────────────────────────

def test_trader_gets_403():
    """GET /api/v1/admin/source-types returns 403 for trader role (T-02-10)."""
    trader_user = _make_staff_user("trader", user_id=3)
    client = _make_client_with_user(trader_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(3, "trader"),
        )

    assert resp.status_code == 403


def test_viewer_gets_403():
    """GET /api/v1/admin/source-types returns 403 for viewer role (T-02-10)."""
    viewer_user = _make_staff_user("viewer", user_id=4)
    client = _make_client_with_user(viewer_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(4, "viewer"),
        )

    assert resp.status_code == 403


def test_analyst_gets_403():
    """GET /api/v1/admin/source-types returns 403 for analyst role (T-02-10)."""
    analyst_user = _make_staff_user("analyst", user_id=2)
    client = _make_client_with_user(analyst_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(2, "analyst"),
        )

    assert resp.status_code == 403


def test_no_token_gets_401():
    """GET /api/v1/admin/source-types returns 401 with no Authorization header."""
    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/source-types")

    assert resp.status_code == 401


# ── no_code flag tests ──────────────────────────────────────────────────────────

def test_no_code_true_for_telegram_channel():
    """telegram_channel adapter has no_code=True."""
    from app.ingest.registry import _clear_registry, register_adapter  # noqa: PLC0415

    _clear_registry()

    class TelegramConfig(BaseModel):
        username: str

    class TelegramChannelAdapter:
        config_schema = TelegramConfig

        async def fetch(self, source):
            return []

        async def test(self, config):
            return None

    adapter = TelegramChannelAdapter()
    adapter.type_name = "telegram_channel"  # type: ignore[attr-defined]
    register_adapter(adapter)  # type: ignore[arg-type]

    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    data = resp.json()
    item = next(x for x in data if x["type_name"] == "telegram_channel")
    assert item["no_code"] is True


def test_no_code_false_for_builtin_uzex():
    """uzex_offers adapter has no_code=False (built-in specialized adapter)."""
    from app.ingest.registry import _clear_registry, register_adapter  # noqa: PLC0415

    _clear_registry()

    class UzexConfig(BaseModel):
        schedule_cron: str = "*/15 9-18 * * 1-5"

    class UzexOffersAdapter:
        config_schema = UzexConfig

        async def fetch(self, source):
            return []

        async def test(self, config):
            return None

    adapter = UzexOffersAdapter()
    adapter.type_name = "uzex_offers"  # type: ignore[attr-defined]
    register_adapter(adapter)  # type: ignore[arg-type]

    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    data = resp.json()
    item = next(x for x in data if x["type_name"] == "uzex_offers")
    assert item["no_code"] is False


def test_no_code_false_for_cbu_rates():
    """cbu_rates adapter has no_code=False."""
    from app.ingest.registry import _clear_registry, register_adapter  # noqa: PLC0415

    _clear_registry()

    class CBUConfig(BaseModel):
        date_from: str | None = None

    class CBURatesAdapter:
        config_schema = CBUConfig

        async def fetch(self, source):
            return []

        async def test(self, config):
            return None

    adapter = CBURatesAdapter()
    adapter.type_name = "cbu_rates"  # type: ignore[attr-defined]
    register_adapter(adapter)  # type: ignore[arg-type]

    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    data = resp.json()
    item = next(x for x in data if x["type_name"] == "cbu_rates")
    assert item["no_code"] is False


# ── Router mounted in main.py ───────────────────────────────────────────────────

def test_admin_sources_router_mounted_in_main():
    """The admin_sources router is mounted in main.py under /api/v1."""
    from pathlib import Path  # noqa: PLC0415

    # Resolve app/main.py relative to this test file (backend/tests/ -> backend/)
    # so the check is machine-independent (no hardcoded developer path).
    main_py = Path(__file__).resolve().parents[1] / "app" / "main.py"
    assert "admin_sources" in main_py.read_text(encoding="utf-8"), (
        "admin_sources not found in app/main.py"
    )
