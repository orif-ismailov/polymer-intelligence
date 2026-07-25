"""Portal E-IMZO API tests (R3 Stage A — TA1.4).

Route registration is DB-free. The challenge/verify behaviour runs against
test_polymer (guarded) with the gateway adapter + S3 mocked, driving real portal
tokens through get_current_account so auth + membership scoping are exercised.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_BASE = "/api/v1/portal/companies"
_PKCS7 = base64.b64encode(b"fake-pkcs7-blob").decode()


def test_routes_registered() -> None:
    from app.api.portal.eimzo import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/eimzo/challenge" in paths
    assert "/portal/companies/{company_id}/eimzo/verify" in paths


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.services.verification_service._dispatch_checks", lambda case_id: None)

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


def _seed_company(session, phone: str, tax: str = "301234567"):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415
    from app.services import company_service, verification_service  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        verification_service.open_case(db, company)
        db.commit()
        company_id, account_id = company.id, account.id
    token = create_portal_access_token(subject=str(account_id))
    return company_id, {"Authorization": f"Bearer {token}"}


def _patch_eimzo(monkeypatch, *, ok=True, org_inn="301234567", raises=False):  # noqa: ANN001
    from app.integrations.eimzo import (  # noqa: PLC0415
        EimzoSigner,
        EimzoVerifyResult,
        ProviderUnavailable,
    )
    from app.services import eimzo_service, storage_service  # noqa: PLC0415

    result = EimzoVerifyResult(
        ok=ok,
        signer=EimzoSigner(
            org_name="OOO Polymer", org_inn=org_inn, full_name="IVANOV IVAN",
            pinfl="31234567890123", position="Director", serial_number="AB",
        ),
        error=None if ok else "signature_invalid",
    )

    def fake_verify(pkcs7, challenge):  # noqa: ANN001, ANN202
        if raises:
            raise ProviderUnavailable("down")
        return result

    monkeypatch.setattr(eimzo_service, "verify_pkcs7", fake_verify)
    monkeypatch.setattr(
        storage_service, "store_eimzo_pkcs7",
        lambda cid, b: (f"evidence/eimzo/{cid}/x.p7s", hashlib.sha256(b).hexdigest()),
    )


@requires_real_db
def test_challenge_and_verify_happy_path(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    _patch_eimzo(monkeypatch)

    ch = client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    assert ch.status_code == 200
    assert len(ch.json()["challenge"]) > 20

    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["holder_masked"] == "****0123"
    chips = {c["check_type"]: c["status"] for c in body["case"]["checks"]}
    assert chips["eimzo_signature"] == "passed"


@requires_real_db
def test_verify_non_member_404(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, _auth = _seed_company(session, "+998900000001")
    _company2, auth_b = _seed_company(session, "+998900000002", tax="309999999")
    _patch_eimzo(monkeypatch)

    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7}, headers=auth_b)
    assert resp.status_code == 404


@requires_real_db
def test_verify_inn_mismatch_422(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001", tax="301234567")
    _patch_eimzo(monkeypatch, org_inn="300000000")

    client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7}, headers=auth)
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "cert_company_mismatch"


@requires_real_db
def test_verify_without_challenge_400(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    _patch_eimzo(monkeypatch)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7}, headers=auth)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "challenge_expired"


@requires_real_db
def test_verify_sidecar_down_503(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    _patch_eimzo(monkeypatch, raises=True)
    client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7}, headers=auth)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "eimzo_unavailable"
