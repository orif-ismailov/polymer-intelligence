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
_SIG_HEX = "ab" * 64


def test_routes_registered() -> None:
    from app.domains.contracts.api_portal_eimzo import router  # noqa: PLC0415

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
    monkeypatch.setattr("app.domains.verification.service._dispatch_checks", lambda case_id: None)

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
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        verification_service.open_case(db, company)
        db.commit()
        company_id, account_id = company.id, account.id
    token = create_portal_access_token(subject=str(account_id))
    return company_id, {"Authorization": f"Bearer {token}"}


def _patch_eimzo(monkeypatch, *, ok=True, org_inn="301234567", raises=None):  # noqa: ANN001
    """Stand in for the Didox identity rail.

    `raises` takes an exception INSTANCE so a test can drive each of the three
    non-verdict exits — outage (503), no Didox account (409) — through the same
    seam. `True` is still accepted and means the outage, which is what every
    caller of this helper meant before those exits existed.
    """
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.edi.identity import DidoxIdentityResult, DidoxSigner  # noqa: PLC0415
    from app.integrations.didox import ProviderUnavailable  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    result = DidoxIdentityResult(
        ok=ok,
        signer=DidoxSigner(
            org_name="OOO Polymer", org_inn=org_inn, full_name="IVANOV IVAN",
            pinfl="31234567890123", position="Director",
        ) if ok else None,
        error=None if ok else "signature_invalid",
    )

    def fake_verify(redis_client, company, *, pkcs7_64, signature_hex, client=None):  # noqa: ANN001, ANN202, ARG001
        if raises:
            raise raises if isinstance(raises, Exception) else ProviderUnavailable("down")
        return result

    monkeypatch.setattr(eimzo_service, "verify_identity", fake_verify)
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

    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX}, headers=auth)
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

    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX}, headers=auth_b)
    assert resp.status_code == 404


@requires_real_db
def test_verify_inn_mismatch_422(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001", tax="301234567")
    _patch_eimzo(monkeypatch, org_inn="300000000")

    client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX}, headers=auth)
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "cert_company_mismatch"


@requires_real_db
def test_verify_without_challenge_400(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    _patch_eimzo(monkeypatch)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX}, headers=auth)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "challenge_expired"


@requires_real_db
def test_verify_sidecar_down_503(api, monkeypatch) -> None:  # noqa: ANN001
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    _patch_eimzo(monkeypatch, raises=True)
    client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    resp = client.post(f"{_BASE}/{company_id}/eimzo/verify", json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX}, headers=auth)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "eimzo_unavailable"


# ── re-confirmation by a company that is already verified ─────────────────────


def _verify(client, company_id, auth):  # noqa: ANN001, ANN202
    client.post(f"{_BASE}/{company_id}/eimzo/challenge", headers=auth)
    return client.post(
        f"{_BASE}/{company_id}/eimzo/verify",
        json={"pkcs7": _PKCS7, "signature_hex": _SIG_HEX},
        headers=auth,
    )


def _approve(session, company_id, *, signer_pinfl=None):  # noqa: ANN001, ANN202
    """Staff approved the onboarding case; optionally a signer is already on file."""
    from app.core.crypto import encrypt_pii  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import CompanyPersonData  # noqa: PLC0415
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415

    with session() as db:
        company = db.get(Company, company_id)
        company.status = CompanyStatus.verified
        case = db.query(VerificationCase).filter(VerificationCase.company_id == company_id).one()
        case.status = VerificationCaseStatus.approved
        if signer_pinfl is not None:
            db.add(CompanyPersonData(
                company_id=company_id, full_name_enc=encrypt_pii("IVANOV IVAN"),
                pinfl_enc=encrypt_pii(signer_pinfl), pinfl_last4=signer_pinfl[-4:],
            ))
        db.commit()
        return case.id


def _cases(session, company_id):  # noqa: ANN001, ANN202
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415

    with session() as db:
        return [
            (c.id, str(c.status))
            for c in db.query(VerificationCase)
            .filter(VerificationCase.company_id == company_id)
            .order_by(VerificationCase.id)
        ]


@requires_real_db
def test_a_verified_company_re_confirming_is_not_queued_for_staff(api, monkeypatch) -> None:  # noqa: ANN001
    """Same key, same ИНН, same director as on file: nothing for a person to
    review. It used to open a «точечная проверка» with a pending manual KYB, so
    every verified company that re-signed showed up twice in /verification."""
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    approved = _approve(session, company_id, signer_pinfl="31234567890123")
    _patch_eimzo(monkeypatch)

    resp = _verify(client, company_id, auth)

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert _cases(session, company_id) == [(approved, "approved")]
    assert resp.json()["case"]["id"] == approved, "the response still names the company's case"


@requires_real_db
def test_a_verified_company_confirming_for_the_first_time_is_not_queued(api, monkeypatch) -> None:  # noqa: ANN001
    """Verified by documents, never signed before: staff already vouched for the
    company, and the signer is the registry's director — nothing new to review."""
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    approved = _approve(session, company_id)
    _patch_eimzo(monkeypatch)

    assert _verify(client, company_id, auth).status_code == 200
    assert _cases(session, company_id) == [(approved, "approved")]


@requires_real_db
def test_a_different_director_still_goes_to_staff(api, monkeypatch) -> None:  # noqa: ANN001
    """A new person signing for the company IS news — that one a human checks."""
    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    approved = _approve(session, company_id, signer_pinfl="39999999999999")
    _patch_eimzo(monkeypatch)

    assert _verify(client, company_id, auth).status_code == 200
    cases = _cases(session, company_id)
    assert len(cases) == 2
    assert cases[0] == (approved, "approved")
    assert cases[1][1] not in {"approved", "draft"}


# ── the ordinary Didox sign-in records who signed ─────────────────────────────


class _DidoxSignIn:
    def __init__(self, director: str = "PETROV PETR", pinfl: str = "32345678901234") -> None:
        self.director, self.pinfl = director, pinfl

    def timestamp(self, pkcs7_64: str, signature_hex: str, **_: object) -> str:
        return "TS"

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = "ru") -> str:
        return "user-key"

    def profile(self, *, user_key: str) -> dict[str, str]:
        return {"tin": "301234567", "director": self.director, "directorPinfl": self.pinfl}


def _people(session, company_id):  # noqa: ANN001, ANN202
    from app.core.crypto import decrypt_pii  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import CompanyPersonData  # noqa: PLC0415

    with session() as db:
        return [
            (decrypt_pii(p.full_name_enc), decrypt_pii(p.pinfl_enc))
            for p in db.query(CompanyPersonData)
            .filter(CompanyPersonData.company_id == company_id)
            .order_by(CompanyPersonData.id)
        ]


@requires_real_db
def test_signing_in_to_didox_records_the_signer(api, monkeypatch) -> None:  # noqa: ANN001
    """It is the SAME signature «Подтвердить личность» asks for — the ИНН, sent to
    Didox's auth. Asking twice, and queueing the second for staff, was the cost."""
    from app.domains.edi import api_portal as edi_api  # noqa: PLC0415
    from app.domains.edi import onboarding  # noqa: PLC0415

    client, session = api
    company_id, auth = _seed_company(session, "+998900000001")
    didox = _DidoxSignIn()
    monkeypatch.setattr(edi_api, "get_didox_client", lambda: didox)
    monkeypatch.setattr(onboarding, "assert_live", lambda: None)
    body = {"pkcs7_64": _PKCS7, "signature_hex": _SIG_HEX}

    assert client.post(f"{_BASE}/{company_id}/didox/session", json=body, headers=auth).status_code == 200
    assert _people(session, company_id) == [("PETROV PETR", "32345678901234")]

    # Every 6 hours is a sign-in; the same person is not a new row each time.
    client.post(f"{_BASE}/{company_id}/didox/session", json=body, headers=auth)
    assert len(_people(session, company_id)) == 1

    didox.director, didox.pinfl = "SIDOROV SIDOR", "33456789012345"
    client.post(f"{_BASE}/{company_id}/didox/session", json=body, headers=auth)
    assert _people(session, company_id)[-1] == ("SIDOROV SIDOR", "33456789012345")
