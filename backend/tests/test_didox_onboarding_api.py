"""Onboarding a verified company onto Didox from the cabinet (24.09.2026).

Three things this pins:

  * **Signing in reads the offer state from the profile it already fetches.**
    `GET /v1/profile` names the signer AND carries `offerSigned`; reading it once
    for both keeps a company that signed the offer on didox.uz from being asked
    to sign it again here, at no extra call to Didox.
  * **Only the owner onboards.** Registering the company at Didox and accepting
    its public offer act for the company; other members see the state only.
  * **The offer can be read before it is signed** — as the PDF Didox publishes.
"""

from __future__ import annotations

import base64

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
_TAX = "301234567"
_SIGNATURE = {"pkcs7_64": base64.b64encode(b"fake-pkcs7").decode(), "signature_hex": "ab" * 64}
_PDF = b"%PDF-1.5 offer"


class _Didox:
    """The slice of the Didox client these routes reach, counting profile reads."""

    def __init__(self, offer_signed: int | None = 1) -> None:
        self.offer_signed = offer_signed
        self.profile_calls = 0

    def timestamp(self, pkcs7_64: str, signature_hex: str, **_: object) -> str:
        return "TS"

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = "ru") -> str:
        return "user-key"

    def signup(self, signature: str, **_: object) -> str:
        return "user-key"

    def profile(self, *, user_key: str) -> dict[str, object]:
        self.profile_calls += 1
        body: dict[str, object] = {"tin": _TAX, "director": "PETROV PETR", "directorPinfl": "32345678901234"}
        if self.offer_signed is not None:
            body["offerSigned"] = self.offer_signed
        return body

    def offer_base64(self, *, user_key: str | None = None) -> str:
        return base64.b64encode(_PDF).decode()


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.domains.edi import onboarding  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.domains.verification.service._dispatch_checks", lambda case_id: None)
    monkeypatch.setattr(onboarding, "_is_live", lambda: True)

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
        yield client, session, fake_redis
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _seed(session) -> tuple[int, dict[str, str], dict[str, str]]:  # noqa: ANN001
    """A company, its owner, and a plain member."""
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.companies.models import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole  # noqa: PLC0415

    with session() as db:
        owner = make_account(db, "+998900000001")
        member = make_account(db, "+998900000002")
        company = company_service.create_company(db, owner, "UZ", _TAX)
        db.add(
            CompanyMember(
                company_id=company.id,
                user_account_id=member.id,
                member_role=CompanyMemberRole.member,
            )
        )
        db.commit()
        return company.id, _auth(owner.id), _auth(member.id)


def _use(monkeypatch, didox: _Didox) -> None:  # noqa: ANN001
    from app.domains.edi import api_portal as edi_api  # noqa: PLC0415

    monkeypatch.setattr(edi_api, "get_didox_client", lambda: didox)


# ── the offer state rides on the sign-in's profile read ──────────────────────


@requires_real_db
def test_signing_in_takes_the_offer_state_from_the_same_profile_read(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, owner, _member = _seed(session)
    didox = _Didox(offer_signed=1)
    _use(monkeypatch, didox)

    signed_in = client.post(f"{_BASE}/{company_id}/didox/session", json=_SIGNATURE, headers=owner)

    assert signed_in.status_code == 200, signed_in.text
    # Signed the offer on didox.uz: nothing left to do here.
    assert signed_in.json()["state"] == "ready"
    assert didox.profile_calls == 1


@requires_real_db
def test_a_profile_saying_unsigned_asks_for_the_offer(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, owner, _member = _seed(session)
    _use(monkeypatch, _Didox(offer_signed=0))

    signed_in = client.post(f"{_BASE}/{company_id}/didox/session", json=_SIGNATURE, headers=owner)

    assert signed_in.json()["state"] == "offer_unsigned"


@requires_real_db
def test_a_profile_without_the_field_leaves_the_offer_as_we_knew_it(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, owner, _member = _seed(session)
    _use(monkeypatch, _Didox(offer_signed=None))

    signed_in = client.post(f"{_BASE}/{company_id}/didox/session", json=_SIGNATURE, headers=owner)

    assert signed_in.json()["state"] == "offer_unsigned"


# ── only the owner onboards ──────────────────────────────────────────────────


@requires_real_db
def test_the_status_says_who_may_onboard(api) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, owner, member = _seed(session)

    assert client.get(f"{_BASE}/{company_id}/didox/status", headers=owner).json()["can_onboard"] is True
    assert client.get(f"{_BASE}/{company_id}/didox/status", headers=member).json()["can_onboard"] is False


@requires_real_db
def test_a_member_cannot_register_the_company_or_accept_the_offer(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, fake_redis = api
    company_id, _owner, member = _seed(session)
    _use(monkeypatch, _Didox())
    fake_redis.set(f"didox:user_key:{_TAX}", "user-key")

    signup = client.post(
        f"{_BASE}/{company_id}/didox/signup",
        json={**_SIGNATURE, "email": "a@b.uz", "mobile": "998900000002", "password": "secret123"},
        headers=member,
    )
    offer = client.post(f"{_BASE}/{company_id}/didox/offer", json=_SIGNATURE, headers=member)

    assert signup.status_code == 403
    assert offer.status_code == 403


@requires_real_db
def test_a_member_can_still_sign_in_to_sign_documents(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, _owner, member = _seed(session)
    _use(monkeypatch, _Didox())

    assert client.post(f"{_BASE}/{company_id}/didox/session", json=_SIGNATURE, headers=member).status_code == 200


# ── the offer can be read before it is signed ────────────────────────────────


@requires_real_db
def test_the_offer_is_readable_as_a_pdf(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, fake_redis = api
    company_id, owner, _member = _seed(session)
    _use(monkeypatch, _Didox())
    fake_redis.set(f"didox:user_key:{_TAX}", "user-key")

    pdf = client.get(f"{_BASE}/{company_id}/didox/offer/pdf", headers=owner)

    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == _PDF


@requires_real_db
def test_reading_the_offer_without_a_session_asks_to_sign_in(api, monkeypatch) -> None:  # noqa: ANN001
    client, session, _ = api
    company_id, owner, _member = _seed(session)
    _use(monkeypatch, _Didox())

    pdf = client.get(f"{_BASE}/{company_id}/didox/offer/pdf", headers=owner)

    assert pdf.status_code == 409
    assert pdf.json()["detail"] == "didox_session_required"
