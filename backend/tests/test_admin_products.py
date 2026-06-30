"""
Tests for the product catalog endpoints:
  - GET/POST/PATCH /api/v1/admin/products   (admin-only CRUD)
  - GET /api/v1/webapp/reference/products    (public webapp selector list)

Fully mocked (MagicMock db + dependency overrides / patched service), mirroring
test_admin_source_types (admin RBAC) and test_marketplace_api (webapp client auth).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.reference import ProductOut

# ── helpers ──────────────────────────────────────────────────────────────────


def _product(id: int = 4, code: str = "LLDPE") -> ProductOut:
    return ProductOut(
        id=id, code=code, name_ru="Линейный ПЭНП", name_uz=None, category="polymer", sort_order=id, is_active=True
    )


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

    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id), role=role)}"}


def _admin_client(staff_user: MagicMock) -> TestClient:
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


# ── admin CRUD ───────────────────────────────────────────────────────────────


def test_admin_list_products_200():
    client = _admin_client(_make_staff_user("admin", 1))
    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.api.admin_products.product_service"
    ) as svc:
        svc.list_all.return_value = [_product()]
        resp = client.get("/api/v1/admin/products", headers=_auth_headers(1, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and data[0]["code"] == "LLDPE"


def test_admin_create_product_201():
    client = _admin_client(_make_staff_user("admin", 1))
    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.api.admin_products.product_service"
    ) as svc:
        svc.create.return_value = _product(id=9, code="EVA")
        resp = client.post(
            "/api/v1/admin/products",
            headers=_auth_headers(1, "admin"),
            json={"code": "EVA", "name_ru": "ЭВА"},
        )
    assert resp.status_code == 201
    assert resp.json()["code"] == "EVA"


def test_admin_update_product_404_when_missing():
    client = _admin_client(_make_staff_user("admin", 1))
    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.api.admin_products.product_service"
    ) as svc:
        svc.get.return_value = None
        resp = client.patch(
            "/api/v1/admin/products/999", headers=_auth_headers(1, "admin"), json={"is_active": False}
        )
    assert resp.status_code == 404


def test_admin_create_duplicate_code_409():
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    client = _admin_client(_make_staff_user("admin", 1))
    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.api.admin_products.product_service"
    ) as svc:
        svc.create.side_effect = IntegrityError("dup", {}, Exception())
        resp = client.post(
            "/api/v1/admin/products",
            headers=_auth_headers(1, "admin"),
            json={"code": "PP", "name_ru": "Полипропилен"},
        )
    assert resp.status_code == 409


@pytest.mark.parametrize("role", ["trader", "viewer", "analyst"])
def test_non_admin_gets_403(role: str):
    client = _admin_client(_make_staff_user(role, 3))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/products", headers=_auth_headers(3, role))
    assert resp.status_code == 403


def test_no_token_gets_401():
    client = _admin_client(_make_staff_user("admin", 1))
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/admin/products")
    assert resp.status_code == 401


# ── public webapp selector list ──────────────────────────────────────────────


def test_webapp_reference_products_200():
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _override_db() -> Generator[Any, None, None]:
        yield MagicMock()

    application = create_app()
    application.dependency_overrides[get_db] = _override_db
    application.dependency_overrides[get_current_client] = lambda: MagicMock()

    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.api.webapp.reference.product_service"
    ) as svc, TestClient(application) as tc:
        svc.list_active.return_value = [_product()]
        resp = tc.get("/api/v1/webapp/reference/products")
    assert resp.status_code == 200
    assert resp.json()[0]["code"] == "LLDPE"


def test_webapp_reference_products_requires_init_data():
    """Without initData the webapp surface rejects the request (401)."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _override_db() -> Generator[Any, None, None]:
        yield MagicMock()

    application = create_app()
    application.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as tc:
        resp = tc.get("/api/v1/webapp/reference/products")
    assert resp.status_code == 401


# ── routers mounted ──────────────────────────────────────────────────────────


def test_routers_mounted_in_main():
    from pathlib import Path  # noqa: PLC0415

    main_py = Path(__file__).resolve().parents[1] / "app" / "main.py"
    text = main_py.read_text(encoding="utf-8")
    assert "admin_products_router" in text
    assert "webapp_reference_router" in text
