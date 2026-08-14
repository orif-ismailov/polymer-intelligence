"""Portal + admin contract API tests (R3 Stage B — TB2.1/TB2.2).

Route registration is DB-free. Behaviour runs against test_polymer (guarded) with
S3/WeasyPrint stubbed and the E-IMZO adapter faked. Covers the authz matrix
(initiator/counterparty/third-company 404), the directory (verified-only), the full
create→send→accept→sign→active flow, the signed bundle, and staff read-only access.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from io import BytesIO

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_P = "/api/v1/portal"
_A = "/api/v1/admin"


def test_routes_registered() -> None:
    from app.domains.contracts.api_admin import router as admin_router  # noqa: PLC0415
    from app.domains.contracts.api_portal import router as portal_router  # noqa: PLC0415

    p = {r.path for r in portal_router.routes}  # type: ignore[attr-defined]
    assert "/portal/contracts" in p
    assert "/portal/contracts/{contract_id}/sign" in p
    assert "/portal/contracts/{contract_id}/bundle" in p
    assert "/portal/contract-templates" in p
    # The counterparty picker is a pure companies query and moved to the companies
    # router in P4. Same path, different owner — and it is now protected by
    # declaration order inside that one file rather than by include-order between two
    # routers, so assert the ordering here: a literal before its param sibling.
    assert "/portal/companies/directory" not in p
    from app.domains.companies.api_portal import router as companies_router  # noqa: PLC0415

    company_paths = [r.path for r in companies_router.routes]  # type: ignore[attr-defined]
    assert "/portal/companies/directory" in company_paths
    assert company_paths.index("/portal/companies/directory") < company_paths.index(
        "/portal/companies/{company_id}"
    ), "/directory must be declared before /{company_id} or the param route swallows it"
    a = {r.path for r in admin_router.routes}  # type: ignore[attr-defined]
    assert "/admin/contracts" in a
    assert "/admin/contracts/{contract_id}" in a


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.integrations.eimzo import EimzoSigner, EimzoVerifyResult  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()

    # Stub S3 + WeasyPrint + E-IMZO adapter (render/crypto are separately tested).
    monkeypatch.setattr(storage_service, "get_object_text", lambda path: "<p>{{ title }}</p>")
    monkeypatch.setattr(contract_render, "render_contract_pdf", lambda *a, **k: b"%PDF-fake-doc")
    monkeypatch.setattr(
        storage_service, "store_contract_pdf",
        lambda pid, n, pdf: (f"contracts/{pid}/contract_v{n}.pdf", hashlib.sha256(pdf).hexdigest()),
    )
    monkeypatch.setattr(
        storage_service, "store_eimzo_pkcs7",
        lambda cid, b: (f"evidence/eimzo/{cid}/x.p7s", hashlib.sha256(b).hexdigest()),
    )
    monkeypatch.setattr(storage_service, "get_object_bytes", lambda key: b"%PDF" if key.endswith(".pdf") else b"p7s")
    monkeypatch.setattr(storage_service, "presign_object", lambda key, ttl=600: f"http://s3.local/{key}?ttl={ttl}")

    def fake_verify(pkcs7, challenge):  # noqa: ANN001, ANN202
        blob = json.loads(base64.b64decode(pkcs7))
        ok = blob.get("challenge") == challenge
        return EimzoVerifyResult(ok=ok, signer=EimzoSigner(org_inn=blob.get("tin")), error=None if ok else "bad")

    monkeypatch.setattr(contract_service, "verify_pkcs7", fake_verify)

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


def _account(session, phone):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        acc = make_account(db, phone)
        db.commit()
        acc_id = acc.id
    return acc_id, {"Authorization": f"Bearer {create_portal_access_token(subject=str(acc_id))}"}


def _verified_company(session, account_id, tax):  # noqa: ANN001, ANN202
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with session() as db:
        acc = db.get(UserAccount, account_id)
        company = company_service.create_company(db, acc, "UZ", tax)
        company.status = CompanyStatus.verified
        company.legal_name = f"OOO {tax}"
        db.commit()
        return company.id


def _staff(session, role, email):  # noqa: ANN001, ANN202
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.enums import StaffRole  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.role = StaffRole(role)
        db.commit()
        sid = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(sid), role=role)}"}


def _template_id(session):  # noqa: ANN001, ANN202
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415

    with session() as db:
        tpl = ContractTemplate(
            code="SUPPLY_TEST", name_ru="Договор", body_storage_path="x",
            variables_schema={"type": "object", "required": ["product"], "properties": {}},
            version=1, is_active=True,
        )
        db.add(tpl)
        db.commit()
        return tpl.id


def _pkcs7(challenge, tin):  # noqa: ANN001, ANN202
    return base64.b64encode(json.dumps({"challenge": challenge, "tin": tin}).encode()).decode()


# ── directory ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_directory_hides_non_verified(api) -> None:  # noqa: ANN001
    client, session = api
    aid, auth = _account(session, "+998900000001")
    _verified_company(session, aid, "301111111")            # verified → listed
    # a draft company (not verified) must not appear
    bid, _ = _account(session, "+998900000002")
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415

    with session() as db:
        company_service.create_company(db, db.get(UserAccount, bid), "UZ", "309999999")
        db.commit()

    res = client.get(f"{_P}/companies/directory", headers=auth)
    assert res.status_code == 200
    taxes = {c["tax_id"] for c in res.json()}
    assert "301111111" in taxes
    assert "309999999" not in taxes


@requires_real_db
def test_directory_lookup_by_id(api) -> None:  # noqa: ANN001
    """Preselecting a counterparty needs an exact door, not a name guess.

    The product page hands over a company id; searching by `q` would depend on the
    seller's legal name matching the ilike, and a short_name never would. The
    verified-only filter still applies — an id is not a way around it.
    """
    client, session = api
    aid, auth = _account(session, "+998900000001")
    verified_id = _verified_company(session, aid, "301111111")

    bid, _ = _account(session, "+998900000002")
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415

    with session() as db:
        draft = company_service.create_company(db, db.get(UserAccount, bid), "UZ", "309999999")
        db.commit()
        draft_id = draft.id

    hit = client.get(
        f"{_P}/companies/directory", params={"company_id": verified_id}, headers=auth
    )
    assert hit.status_code == 200
    assert [c["id"] for c in hit.json()] == [verified_id]

    miss = client.get(
        f"{_P}/companies/directory", params={"company_id": draft_id}, headers=auth
    )
    assert miss.status_code == 200
    assert miss.json() == []


# ── authz matrix + full flow ──────────────────────────────────────────────────


@requires_real_db
def test_full_contract_flow_and_authz(api) -> None:  # noqa: ANN001
    client, session = api
    a_id, a_auth = _account(session, "+998900000001")
    b_id, b_auth = _account(session, "+998900000002")
    c_id, c_auth = _account(session, "+998900000003")  # unrelated third party
    initiator = _verified_company(session, a_id, "301111111")
    counterparty = _verified_company(session, b_id, "302222222")
    _verified_company(session, c_id, "303333333")
    tpl = _template_id(session)

    # create (initiator)
    created = client.post(
        f"{_P}/contracts",
        json={
            "initiator_company_id": initiator,
            "counterparty_company_id": counterparty,
            "template_id": tpl,
            "variables": {"product": "HDPE"},
        },
        headers=a_auth,
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["status"] == "draft"

    # third company cannot see it → 404
    assert client.get(f"{_P}/contracts/{cid}", headers=c_auth).status_code == 404
    # counterparty cannot send (only initiator) → 403
    assert client.post(f"{_P}/contracts/{cid}/send", headers=b_auth).status_code == 403

    # initiator sends → pending_counterparty
    assert client.post(f"{_P}/contracts/{cid}/send", headers=a_auth).json()["status"] == "pending_counterparty"
    # initiator cannot accept (only counterparty) → 403
    assert client.post(f"{_P}/contracts/{cid}/accept", headers=a_auth).status_code == 403
    # counterparty accepts → pending_signatures
    assert client.post(f"{_P}/contracts/{cid}/accept", headers=b_auth).json()["status"] == "pending_signatures"

    # both sign
    for auth, tin in ((a_auth, "301111111"), (b_auth, "302222222")):
        ch = client.post(f"{_P}/contracts/{cid}/sign/challenge", headers=auth).json()["challenge"]
        signed = client.post(f"{_P}/contracts/{cid}/sign", json={"pkcs7": _pkcs7(ch, tin)}, headers=auth)
        assert signed.status_code == 200, signed.text
    assert client.get(f"{_P}/contracts/{cid}", headers=a_auth).json()["status"] == "active"

    # bundle contains pdf + 2 signatures + verification.json
    bundle = client.get(f"{_P}/contracts/{cid}/bundle", headers=a_auth)
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(BytesIO(bundle.content)).namelist()
    assert "contract.pdf" in names
    assert "verification.json" in names
    assert sum(1 for n in names if n.endswith(".p7s")) == 2

    # staff read-only oversight
    staff = _staff(session, "analyst", "a@x.com")
    lst = client.get(f"{_A}/contracts", headers=staff)
    assert lst.status_code == 200 and any(c["id"] == cid for c in lst.json())
    detail = client.get(f"{_A}/contracts/{cid}", headers=staff)
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    assert len(detail.json()["signatures"]) == 2
    assert len(detail.json()["timeline"]) >= 1  # audit trail present


@requires_real_db
def test_sign_inn_mismatch_422(api) -> None:  # noqa: ANN001
    client, session = api
    a_id, a_auth = _account(session, "+998900000001")
    b_id, b_auth = _account(session, "+998900000002")
    initiator = _verified_company(session, a_id, "301111111")
    counterparty = _verified_company(session, b_id, "302222222")
    tpl = _template_id(session)
    cid = client.post(
        f"{_P}/contracts",
        json={"initiator_company_id": initiator, "counterparty_company_id": counterparty,
              "template_id": tpl, "variables": {"product": "HDPE"}},
        headers=a_auth,
    ).json()["id"]
    client.post(f"{_P}/contracts/{cid}/send", headers=a_auth)
    client.post(f"{_P}/contracts/{cid}/accept", headers=b_auth)
    ch = client.post(f"{_P}/contracts/{cid}/sign/challenge", headers=a_auth).json()["challenge"]
    res = client.post(f"{_P}/contracts/{cid}/sign", json={"pkcs7": _pkcs7(ch, "300000000")}, headers=a_auth)
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "cert_company_mismatch"


@requires_real_db
def test_create_counterparty_must_be_verified_422(api) -> None:  # noqa: ANN001
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415

    client, session = api
    a_id, a_auth = _account(session, "+998900000001")
    initiator = _verified_company(session, a_id, "301111111")
    tpl = _template_id(session)
    # a draft (unverified) counterparty
    b_id, _ = _account(session, "+998900000002")
    with session() as db:
        cp = company_service.create_company(db, db.get(UserAccount, b_id), "UZ", "302222222")
        db.commit()
        cp_id = cp.id
    res = client.post(
        f"{_P}/contracts",
        json={"initiator_company_id": initiator, "counterparty_company_id": cp_id,
              "template_id": tpl, "variables": {"product": "HDPE"}},
        headers=a_auth,
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "counterparty_not_verified"
