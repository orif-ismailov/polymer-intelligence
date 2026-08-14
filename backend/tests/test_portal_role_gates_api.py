"""Business-role gates on the portal write endpoints (role-based cabinet, T-B).

A company registers as ONE account type (buyer / distributor-trader /
manufacturer / logistics / laboratory) and the API refuses the writes outside
that type's feature set with 403 `{"code": "role_not_allowed"}` — the UI hides
the same features, but a curl or a stale tab reaches this same route.

The gates read the NON-REVOKED role set (declared or confirmed): a draft
laboratory is already a laboratory to the cabinet, before staff vouch for it.
A company with no gateable roles at all (legacy rows) falls back to the buyer
view — fail open, the same philosophy as `RequireCompany` in the portal.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

_API = "/api/v1"


# ── fixture (portal-companies shape: real DB + fake redis) ────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
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


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


_TAX_SEQ = iter(f"42{n:07d}" for n in range(1, 1000))


def _company_with_roles(db, phone, roles, *, verified=True):  # noqa: ANN001, ANN202
    """A company holding `roles` (as declared+confirmed mix doesn't matter to the gate)."""
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415

    owner = make_account(db, phone)
    company = make_company(
        db,
        owner,
        tax_id=next(_TAX_SEQ),
        status=CompanyStatus.verified if verified else CompanyStatus.draft,
    )
    for role in roles:
        db.add(
            CompanyBusinessRole(
                company_id=company.id, role=role, status=BusinessRoleStatus.declared
            )
        )
    db.flush()
    return owner.id, company.id


def _assert_role_403(resp) -> None:  # noqa: ANN001
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "role_not_allowed"


_OFFER = {"product_text": "HDPE 5502", "grade_text": "film", "price": "1200", "currency": "USD"}

_REQUEST = {
    "product_text": "HDPE film grade",
    "grade_text": "F0348",
    "polymer_type": "HDPE",
    "volume": "50.000",
    "volume_unit": "MT",
    "urgency": "high",
}

_LAB_REQUEST = {
    "product_text": "HDPE S5502 BN",
    "study_type": "full_passport",
    "methods": ["mfi", "density"],
}

_LOGISTICS_REQUEST = {
    "cargo_name": "Полипропилен (PP)",
    "volume": "500",
    "volume_unit": "MT",
    "from_country": "CN",
    "to_country": "UZ",
}


# ── seller-side gates (offers, RFQ inbox) ─────────────────────────────────────


@requires_real_db
def test_offer_create_is_seller_only(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        lab_owner, lab_id = _company_with_roles(db, "+998900030001", [Role.laboratory])
        dist_owner, dist_id = _company_with_roles(db, "+998900030002", [Role.distributor, Role.trader])
        buyer_owner, buyer_id = _company_with_roles(db, "+998900030003", [Role.importer])
        db.commit()

    _assert_role_403(
        client.post(f"{_API}/portal/companies/{lab_id}/offers", json=_OFFER, headers=_auth(lab_owner))
    )
    _assert_role_403(
        client.post(f"{_API}/portal/companies/{buyer_id}/offers", json=_OFFER, headers=_auth(buyer_owner))
    )
    created = client.post(
        f"{_API}/portal/companies/{dist_id}/offers", json=_OFFER, headers=_auth(dist_owner)
    )
    assert created.status_code == 201, created.text


@requires_real_db
def test_offer_create_zero_roles_falls_back_to_buyer_and_is_refused(api) -> None:  # noqa: ANN001
    """Legacy company with no role rows = buyer view → no publishing."""
    client, session = api
    with session() as db:
        owner, company_id = _company_with_roles(db, "+998900030001", [])
        db.commit()

    _assert_role_403(
        client.post(f"{_API}/portal/companies/{company_id}/offers", json=_OFFER, headers=_auth(owner))
    )


@requires_real_db
def test_offer_update_is_seller_only(api) -> None:  # noqa: ANN001
    """A pre-gating offer row owned by a non-seller can no longer be edited."""
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner, company_id = _company_with_roles(db, "+998900030001", [Role.logistics_provider])
        offer = make_seller_offer(db, company=db.get(Company, company_id))
        offer_id = offer.id
        db.commit()

    _assert_role_403(
        client.patch(
            f"{_API}/portal/companies/{company_id}/offers/{offer_id}",
            json=_OFFER,
            headers=_auth(owner),
        )
    )


@requires_real_db
def test_rfq_response_is_seller_only(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner, buyer_id = _company_with_roles(db, "+998900030001", [Role.importer])
        buyer_acc = make_account(db, "+998900030009")
        request = make_request(db, company=db.get(Company, buyer_id), account=buyer_acc)
        request_id = request.id
        lab_owner, lab_id = _company_with_roles(db, "+998900030002", [Role.laboratory])
        mfr_owner, mfr_id = _company_with_roles(db, "+998900030003", [Role.manufacturer])
        db.commit()

    quote = {"price": "1250.00", "currency": "USD", "qty": "20", "qty_unit": "MT"}
    _assert_role_403(
        client.post(
            f"{_API}/portal/companies/{lab_id}/requests/{request_id}/responses",
            json=quote,
            headers=_auth(lab_owner),
        )
    )
    ok = client.post(
        f"{_API}/portal/companies/{mfr_id}/requests/{request_id}/responses",
        json=quote,
        headers=_auth(mfr_owner),
    )
    assert ok.status_code == 201, ok.text


# ── buyer-side gates (requests, inquiries, samples, factory) ──────────────────


@requires_real_db
def test_purchase_request_is_refused_for_service_roles(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        lab_owner, lab_id = _company_with_roles(db, "+998900030001", [Role.laboratory])
        log_owner, log_id = _company_with_roles(db, "+998900030002", [Role.logistics_provider])
        zero_owner, zero_id = _company_with_roles(db, "+998900030003", [], verified=False)
        db.commit()

    _assert_role_403(
        client.post(
            f"{_API}/portal/requests", json={**_REQUEST, "company_id": lab_id}, headers=_auth(lab_owner)
        )
    )
    _assert_role_403(
        client.post(
            f"{_API}/portal/requests", json={**_REQUEST, "company_id": log_id}, headers=_auth(log_owner)
        )
    )
    # zero-role legacy company (even a draft one) = buyer view → allowed
    ok = client.post(
        f"{_API}/portal/requests", json={**_REQUEST, "company_id": zero_id}, headers=_auth(zero_owner)
    )
    assert ok.status_code == 201, ok.text


@requires_real_db
def test_inquiry_is_refused_for_service_roles(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        seller_owner, seller_id = _company_with_roles(db, "+998900030001", [Role.distributor])
        offer = make_seller_offer(db, company=db.get(Company, seller_id))
        offer_id = offer.id
        lab_owner, lab_id = _company_with_roles(db, "+998900030002", [Role.laboratory])
        db.commit()

    _assert_role_403(
        client.post(
            f"{_API}/portal/market/{offer_id}/inquiries",
            json={"company_id": lab_id, "quantity": "20", "message": "?"},
            headers=_auth(lab_owner),
        )
    )


@requires_real_db
def test_sample_request_is_refused_for_service_roles(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        log_owner, log_id = _company_with_roles(db, "+998900030001", [Role.logistics_provider])
        db.commit()

    # the role gate fires before the offer lookup — no offer fixture needed
    _assert_role_403(
        client.post(
            f"{_API}/portal/market/offers/999999/samples",
            json={"company_id": log_id, "delivery_address": "Ташкент", "qty": "1 кг"},
            headers=_auth(log_owner),
        )
    )


@requires_real_db
def test_factory_chat_and_rfq_are_refused_for_service_roles(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        lab_owner, lab_id = _company_with_roles(db, "+998900030001", [Role.laboratory])
        log_owner, log_id = _company_with_roles(db, "+998900030002", [Role.logistics_provider])
        db.commit()

    _assert_role_403(
        client.post(
            f"{_API}/portal/manufacturers/999999/threads",
            json={"company_id": lab_id},
            headers=_auth(lab_owner),
        )
    )
    _assert_role_403(
        client.post(
            f"{_API}/portal/manufacturers/999999/rfqs",
            json={
                "company_id": log_id,
                "offer_id": 1,
                "quantity": "20",
                "contact_name": "Азиз",
                "contact_phone": "+998901112233",
            },
            headers=_auth(log_owner),
        )
    )


# ── service-ordering gates (cross-service allowed, own service refused) ───────


@requires_real_db
def test_lab_request_gate_cross_service(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        # a DRAFT laboratory (declared only) — proves the gate reads declared roles
        lab_owner, lab_id = _company_with_roles(db, "+998900030001", [Role.laboratory], verified=False)
        log_owner, log_id = _company_with_roles(db, "+998900030002", [Role.logistics_provider])
        db.commit()

    _assert_role_403(
        client.post(
            f"{_API}/portal/lab/requests",
            json={**_LAB_REQUEST, "company_id": lab_id},
            headers=_auth(lab_owner),
        )
    )
    # a carrier ordering an analysis is cross-service — allowed
    ok = client.post(
        f"{_API}/portal/lab/requests",
        json={**_LAB_REQUEST, "company_id": log_id},
        headers=_auth(log_owner),
    )
    assert ok.status_code == 201, ok.text


@requires_real_db
def test_logistics_request_gate_cross_service(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        log_owner, log_id = _company_with_roles(db, "+998900030001", [Role.logistics_provider])
        lab_owner, lab_id = _company_with_roles(db, "+998900030002", [Role.laboratory])
        db.commit()

    _assert_role_403(
        client.post(
            f"{_API}/portal/logistics/requests",
            json={**_LOGISTICS_REQUEST, "company_id": log_id},
            headers=_auth(log_owner),
        )
    )
    # a laboratory shipping samples is cross-service — allowed
    ok = client.post(
        f"{_API}/portal/logistics/requests",
        json={**_LOGISTICS_REQUEST, "company_id": lab_id},
        headers=_auth(lab_owner),
    )
    assert ok.status_code == 201, ok.text
