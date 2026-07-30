"""Portal company-logo API tests (P1 W1 — T1.3).

Route registration is DB-free. Upload/replace/delete, RBAC (owner+manager may,
plain member may not, non-member gets 404) and the presigned `logo_url` run
against test_polymer (guarded) so real portal tokens go through
get_current_account and the membership/role scoping is exercised end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/companies"

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG = b"\xff\xd8\xff" + b"\x00" * 64
_PDF = b"%PDF-1.4 not a picture"


def test_routes_registered() -> None:
    from app.api.portal.companies import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/logo" in paths


# ── real-DB API fixture ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _seed_account(session, phone: str) -> tuple[int, dict[str, str]]:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    token = create_portal_access_token(subject=str(account_id))
    return account_id, {"Authorization": f"Bearer {token}"}


def _add_member(session, company_id: int, account_id: int, role: str) -> None:  # noqa: ANN001
    from app.models.companies import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415

    with session() as db:
        db.add(
            CompanyMember(
                company_id=company_id,
                user_account_id=account_id,
                member_role=CompanyMemberRole(role),
                status=CompanyMemberStatus.active,
            )
        )
        db.commit()


def _company_for(client, auth: dict[str, str], tax_id: str) -> int:  # noqa: ANN001
    created = client.post(_BASE, json={"tax_id": tax_id}, headers=auth)
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


# ── Upload / replace / delete ────────────────────────────────────────────────


@requires_real_db
def test_owner_uploads_logo_and_gets_a_loadable_url(api) -> None:  # noqa: ANN001
    """`logo_url` points at the API's own proxy route, not at a presigned S3 link.

    S3_ENDPOINT is the object store's INTERNAL address, so a presigned URL is signed
    against a host the browser cannot resolve — it would render as a broken image.
    """
    client, session = api
    _aid, auth = _seed_account(session, "+998900000101")
    company_id = _company_for(client, auth, "111111111")

    expected = f"/api/v1/webapp/market/companies/{company_id}/logo"
    fake_s3 = MagicMock()
    with patch("app.core.storage.s3_client", fake_s3):
        res = client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("logo.png", _PNG, "image/png")},
            headers=auth,
        )
        assert res.status_code == 201, res.text
        assert res.json()["logo_url"] == expected

        # It survives a re-read.
        detail = client.get(f"{_BASE}/{company_id}", headers=auth)
        assert detail.json()["logo_url"] == expected

    fake_s3.put_object.assert_called_once()
    # No signature is minted any more — the proxy route carries none to expire.
    fake_s3.generate_presigned_url.assert_not_called()


@requires_real_db
def test_no_logo_means_null_url_not_an_error(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000102")
    company_id = _company_for(client, auth, "222222222")

    detail = client.get(f"{_BASE}/{company_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["logo_url"] is None


@requires_real_db
def test_replace_then_delete(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000103")
    company_id = _company_for(client, auth, "333333333")

    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = "https://s3.example/x"
    with patch("app.core.storage.s3_client", fake_s3):
        client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("a.png", _PNG, "image/png")},
            headers=auth,
        )
        client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("b.jpg", _JPEG, "image/jpeg")},
            headers=auth,
        )
        # The first object is cleaned up on replace.
        assert fake_s3.delete_object.call_count == 1

        deleted = client.delete(f"{_BASE}/{company_id}/logo", headers=auth)
        assert deleted.status_code == 204
        assert fake_s3.delete_object.call_count == 2

        detail = client.get(f"{_BASE}/{company_id}", headers=auth)
        assert detail.json()["logo_url"] is None


@requires_real_db
def test_delete_without_a_logo_is_idempotent(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000104")
    company_id = _company_for(client, auth, "444444444")

    with patch("app.core.storage.s3_client"):
        assert client.delete(f"{_BASE}/{company_id}/logo", headers=auth).status_code == 204


# ── Validation ───────────────────────────────────────────────────────────────


@requires_real_db
def test_pdf_disguised_as_png_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000105")
    company_id = _company_for(client, auth, "555555555")

    fake_s3 = MagicMock()
    with patch("app.core.storage.s3_client", fake_s3):
        res = client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("logo.png", _PDF, "image/png")},
            headers=auth,
        )
    assert res.status_code == 422
    assert res.json()["detail"] == "invalid_file_type"
    fake_s3.put_object.assert_not_called()


@requires_real_db
def test_oversized_logo_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000106")
    company_id = _company_for(client, auth, "666666666")

    oversized = _PNG + b"\x00" * (5 * 1024 * 1024)
    fake_s3 = MagicMock()
    with patch("app.core.storage.s3_client", fake_s3):
        res = client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("big.png", oversized, "image/png")},
            headers=auth,
        )
    assert res.status_code == 422
    assert res.json()["detail"] == "file_too_large"
    fake_s3.put_object.assert_not_called()


# ── RBAC ─────────────────────────────────────────────────────────────────────


@requires_real_db
def test_manager_may_upload_but_plain_member_may_not(api) -> None:  # noqa: ANN001
    client, session = api
    _owner_id, owner_auth = _seed_account(session, "+998900000107")
    company_id = _company_for(client, owner_auth, "777777777")

    manager_id, manager_auth = _seed_account(session, "+998900000108")
    member_id, member_auth = _seed_account(session, "+998900000109")
    _add_member(session, company_id, manager_id, "manager")
    _add_member(session, company_id, member_id, "member")

    with patch("app.core.storage.s3_client", MagicMock()):
        assert (
            client.post(
                f"{_BASE}/{company_id}/logo",
                files={"file": ("logo.png", _PNG, "image/png")},
                headers=manager_auth,
            ).status_code
            == 201
        )
        # A plain member can see the company but must not change its branding.
        assert client.get(f"{_BASE}/{company_id}", headers=member_auth).status_code == 200
        assert (
            client.post(
                f"{_BASE}/{company_id}/logo",
                files={"file": ("logo.png", _PNG, "image/png")},
                headers=member_auth,
            ).status_code
            == 403
        )
        assert client.delete(f"{_BASE}/{company_id}/logo", headers=member_auth).status_code == 403


@requires_real_db
def test_non_member_gets_404_not_403(api) -> None:  # noqa: ANN001
    """Company existence must not leak to outsiders (IDOR-safe, as elsewhere)."""
    client, session = api
    _owner_id, owner_auth = _seed_account(session, "+998900000110")
    company_id = _company_for(client, owner_auth, "888888888")
    _outsider_id, outsider_auth = _seed_account(session, "+998900000111")

    with patch("app.core.storage.s3_client", MagicMock()):
        res = client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("logo.png", _PNG, "image/png")},
            headers=outsider_auth,
        )
    assert res.status_code == 404


# ── Audit ────────────────────────────────────────────────────────────────────


@requires_real_db
def test_upload_and_delete_are_audited(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000112")
    company_id = _company_for(client, auth, "999999991")

    with patch("app.core.storage.s3_client", MagicMock()):
        client.post(
            f"{_BASE}/{company_id}/logo",
            files={"file": ("logo.png", _PNG, "image/png")},
            headers=auth,
        )
        client.delete(f"{_BASE}/{company_id}/logo", headers=auth)

    from app.models.staff import AuditLog  # noqa: PLC0415

    with session() as db:
        actions = [
            row.action
            for row in db.query(AuditLog)
            .filter(AuditLog.entity == "company", AuditLog.entity_id == str(company_id))
            .order_by(AuditLog.id)
            .all()
        ]
    assert "company.logo_upload" in actions
    assert "company.logo_delete" in actions
