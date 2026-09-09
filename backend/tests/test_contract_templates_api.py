"""Contract-template authoring against a real database: versioning + authz.

Complements `test_contract_templates.py` (pure validation). Everything here needs
rows and an S3 double: the versioning contract is about what happens to
`body_storage_path` and to the OLD object, which is not observable in isolation.

Guarded on `test_polymer` like the other real-DB suites.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_engine,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_A = "/api/v1/admin/contract-templates"

_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["product"],
    "properties": {"product": {"type": "string", "title": "Товар"}},
}
_BODY = "<h2>Стороны</h2><p>{{ initiator_legal_name }} — {{ product }}</p>"


class _FakeS3:
    """Keyed object store. Enough to prove an old version SURVIVES a bump, which a
    MagicMock cannot show."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {"ETag": "x"}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key not in self.objects:
            raise KeyError(key)
        return {"Body": _Body(self.objects[key])}


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def test_routes_registered() -> None:
    """DB-free: the six routes exist and are mounted under /admin."""
    from app.domains.contracts.api_admin import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/contract-templates" in paths
    assert "/admin/contract-templates/{template_id}" in paths
    assert "/admin/contract-templates/{template_id}/active" in paths
    assert "/admin/contract-templates/check" in paths
    assert "/admin/contract-templates/preview" in paths


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, Any, _FakeS3]]:
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    migrate_head()
    engine = make_engine()
    clean(engine)
    session = session_factory(engine)
    fake_s3 = _FakeS3()

    monkeypatch.setattr("app.core.storage.s3_client", fake_s3)
    app = create_app()

    def _override_db() -> Generator[Any]:
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session, fake_s3
    clean(engine)


def _staff_headers(
    session: Any, *, email: str, admin: bool, page: str | None = "contracts"
) -> dict[str, str]:
    """A staff token. Non-admins get an explicit `contracts` grant.

    `require_page` treats absence as denial, and `make_staff` grants nothing — so a
    non-admin without this row is 403 on every route here, which would make the
    authz tests below pass for the wrong reason.
    """
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.staff import StaffPageAccess  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.is_admin = admin
        db.flush()
        if not admin and page is not None:
            db.add(StaffPageAccess(staff_user_id=staff.id, page=page, access="write"))
        db.commit()
        sid = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(sid))}"}


@requires_real_db
class TestVersioning:
    def test_create_starts_at_version_one(self, api: Any) -> None:
        client, session, s3 = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)

        created = client.post(
            _A,
            json={"code": "SUPPLY_T1", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        )

        assert created.status_code == 201, created.text
        assert created.json()["version"] == 1
        assert "contracts/templates/SUPPLY_T1_v1.html" in s3.objects

    def test_a_body_change_bumps_the_version_and_keeps_the_old_object(
        self, api: Any
    ) -> None:
        """The reason a contract can still be shown the bytes it was created from:
        `(template_id, template_version)` resolves to a key that still exists."""
        client, session, s3 = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)
        tid = client.post(
            _A,
            json={"code": "SUPPLY_T2", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        ).json()["id"]

        updated = client.put(
            f"{_A}/{tid}",
            json={"name_ru": "Договор", "body": _BODY + "<p>{{ product }}</p>",
                  "variables_schema": _SCHEMA, "is_active": True},
            headers=auth,
        )

        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2
        assert "contracts/templates/SUPPLY_T2_v1.html" in s3.objects, "v1 was destroyed"
        assert "contracts/templates/SUPPLY_T2_v2.html" in s3.objects

    def test_metadata_only_save_does_not_bump(self, api: Any) -> None:
        """Re-saving a name must not manufacture a revision nobody authored."""
        client, session, _ = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)
        tid = client.post(
            _A,
            json={"code": "SUPPLY_T3", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        ).json()["id"]

        updated = client.put(
            f"{_A}/{tid}",
            json={"name_ru": "Договор поставки", "body": _BODY,
                  "variables_schema": _SCHEMA, "is_active": True},
            headers=auth,
        )

        assert updated.json()["version"] == 1
        assert updated.json()["name_ru"] == "Договор поставки"

    def test_duplicate_code_is_a_409(self, api: Any) -> None:
        client, session, _ = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)
        payload = {"code": "SUPPLY_T4", "name_ru": "Договор", "body": _BODY,
                   "variables_schema": _SCHEMA}
        client.post(_A, json=payload, headers=auth)

        again = client.post(_A, json=payload, headers=auth)

        assert again.status_code == 409
        assert again.json()["detail"]["error"] == "duplicate_code"

    def test_an_unrenderable_placeholder_is_refused_and_writes_nothing(
        self, api: Any
    ) -> None:
        """422 BEFORE S3 — a rejected body must not leave an orphan object behind."""
        client, session, s3 = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)

        refused = client.post(
            _A,
            json={"code": "SUPPLY_T5", "name_ru": "Договор",
                  "body": "<p>{{ buyer_nmae }}</p>", "variables_schema": _SCHEMA},
            headers=auth,
        )

        assert refused.status_code == 422
        assert refused.json()["detail"]["unknown"] == ["buyer_nmae"]
        assert not any("SUPPLY_T5" in k for k in s3.objects)

    def test_deactivating_hides_it_from_the_cabinet(self, api: Any) -> None:
        """`GET /portal/contract-templates` filters on `is_active`; the row is never
        deleted because contracts hold an FK to it."""
        client, session, _ = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)
        tid = client.post(
            _A,
            json={"code": "SUPPLY_T6", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        ).json()["id"]

        client.patch(f"{_A}/{tid}/active", json={"is_active": False}, headers=auth)

        active = client.get(f"{_A}?include_inactive=false", headers=auth).json()
        assert not any(t["id"] == tid for t in active)
        assert any(t["id"] == tid for t in client.get(_A, headers=auth).json())


@requires_real_db
class TestAuthz:
    """Reads follow the `contracts` page grant; writes need an administrator.

    These bodies are the legal text two companies e-sign — handing someone the
    contracts page must not hand them the power to rewrite it.
    """

    def test_non_admin_staff_may_read(self, api: Any) -> None:
        client, session, _ = api
        auth = _staff_headers(session, email="analyst@x.uz", admin=False)

        assert client.get(_A, headers=auth).status_code == 200

    def test_non_admin_staff_may_not_create(self, api: Any) -> None:
        client, session, _ = api
        auth = _staff_headers(session, email="analyst@x.uz", admin=False)

        created = client.post(
            _A,
            json={"code": "SUPPLY_T7", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        )

        assert created.status_code == 403

    def test_non_admin_staff_may_not_update_or_deactivate(self, api: Any) -> None:
        client, session, _ = api
        admin = _staff_headers(session, email="a@x.uz", admin=True)
        analyst = _staff_headers(session, email="analyst@x.uz", admin=False)
        tid = client.post(
            _A,
            json={"code": "SUPPLY_T8", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=admin,
        ).json()["id"]

        put = client.put(
            f"{_A}/{tid}",
            json={"name_ru": "x", "variables_schema": _SCHEMA, "is_active": True},
            headers=analyst,
        )
        patch_ = client.patch(f"{_A}/{tid}/active", json={"is_active": False}, headers=analyst)

        assert put.status_code == 403
        assert patch_.status_code == 403

    def test_anonymous_is_refused(self, api: Any) -> None:
        client, _, _ = api

        assert client.get(_A).status_code in (401, 403)


@requires_real_db
class TestAudit:
    def test_a_write_is_recorded(self, api: Any) -> None:
        """Legal text: who changed it and when has to be answerable."""
        from app.models.staff import AuditLog  # noqa: PLC0415

        client, session, _ = api
        auth = _staff_headers(session, email="a@x.uz", admin=True)

        client.post(
            _A,
            json={"code": "SUPPLY_T9", "name_ru": "Договор", "body": _BODY,
                  "variables_schema": _SCHEMA},
            headers=auth,
        )

        with session() as db:
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.entity == "contract_templates")
                .all()
            )
        assert [r.action for r in rows] == ["contract_template.create"]
        assert rows[0].staff_user_id is not None


@requires_real_db
class TestCheckAndPreview:
    def test_check_reports_unknown_without_saving(self, api: Any) -> None:
        client, session, _ = api
        auth = _staff_headers(session, email="analyst@x.uz", admin=False)

        result = client.post(
            f"{_A}/check",
            json={"body": "<p>{{ nope }}</p>", "kind": "contract", "variables_schema": {}},
            headers=auth,
        ).json()

        assert result["ok"] is False
        assert result["unknown"] == ["nope"]
        assert "initiator_legal_name" in result["renderable"]

    def test_preview_uses_visible_stand_ins(self, api: Any) -> None:
        client, session, _ = api
        auth = _staff_headers(session, email="analyst@x.uz", admin=False)

        result = client.post(
            f"{_A}/preview",
            json={"body": _BODY, "kind": "contract", "variables_schema": _SCHEMA},
            headers=auth,
        ).json()

        assert "[initiator_legal_name]" in result["html"]
        assert "[Товар]" in result["html"]
