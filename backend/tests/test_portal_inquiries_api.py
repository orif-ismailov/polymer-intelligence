"""Portal inquiries API tests (R2 W3 T3.2).

Route reg DB-free; the rest against test_polymer (guarded): send an inquiry
(pending → moderation), list sent/incoming, cross-company isolation (member of A
cannot list B's inquiries — 404), and edit-resubmit re-entering moderation.
REQUEST_NOTIFY_CHAT_ID is unset in tests, so the group-notify enqueue no-ops.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal"


def test_inquiry_routes_registered() -> None:
    from app.domains.marketplace.api_portal_inquiries import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/market/{offer_id}/inquiries" in paths
    assert "/portal/inquiries" in paths
    assert "/portal/inquiries/incoming" in paths
    assert "/portal/inquiries/{inquiry_id}" in paths


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from unittest.mock import patch  # noqa: PLC0415

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


@requires_real_db
def test_send_inquiry_creates_pending(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005001")
        selling_co = make_company(db, seller_owner, tax_id="315000001")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900005002")
        buyer_co = make_company(db, buyer_owner, tax_id="315000002")
        db.commit()
        buyer_owner_id, buyer_co_id, offer_id = buyer_owner.id, buyer_co.id, offer.id

    resp = client.post(
        f"{_BASE}/market/{offer_id}/inquiries",
        json={"company_id": buyer_co_id, "quantity": "15.000", "message": "please advise"},
        headers=_auth(buyer_owner_id),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["offer_id"] == offer_id
    # buyer-facing view — no moderation internals leak
    assert "moderation_note" not in body
    assert "moderated_by" not in body

    sent = client.get(
        f"{_BASE}/inquiries", params={"company_id": buyer_co_id}, headers=_auth(buyer_owner_id)
    )
    assert sent.status_code == 200
    assert len(sent.json()) == 1


@requires_real_db
def test_sent_list_cross_company_isolation(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        a_owner = make_account(db, "+998900005100")
        make_company(db, a_owner, tax_id="315000100")
        b_owner = make_account(db, "+998900005101")
        company_b = make_company(db, b_owner, tax_id="315000101")
        db.commit()
        a_owner_id, company_b_id = a_owner.id, company_b.id

    # A acting, claims B's id → 404 (no cross-company disclosure)
    resp = client.get(
        f"{_BASE}/inquiries", params={"company_id": company_b_id}, headers=_auth(a_owner_id)
    )
    assert resp.status_code == 404


@requires_real_db
def test_edit_inquiry_reenters_moderation(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005200")
        selling_co = make_company(db, seller_owner, tax_id="315000200")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900005201")
        buyer_co = make_company(db, buyer_owner, tax_id="315000201")
        from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
        from app.domains.marketplace.schemas import OfferRequestCreate  # noqa: PLC0415
        from app.models.enums import OfferRequestStatus  # noqa: PLC0415

        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, OfferRequestCreate(quantity=None, message="v1"),
        )
        # approve it so an edit demonstrably re-enters moderation
        offer_request_service.moderate_offer_request(db, req, staff_user_id=None, approve=True)
        db.commit()
        assert req.status == OfferRequestStatus.approved
        buyer_owner_id, buyer_co_id, inquiry_id = buyer_owner.id, buyer_co.id, req.id

    resp = client.patch(
        f"{_BASE}/inquiries/{inquiry_id}",
        json={"company_id": buyer_co_id, "quantity": None, "message": "v2 revised"},
        headers=_auth(buyer_owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"  # re-entered moderation


@requires_real_db
def test_inquiry_daily_rate_limit(api) -> None:  # noqa: ANN001
    """The 11th inquiry in a day for a company is rejected with 429 (R2 W6 T6.1)."""
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005400")
        selling_co = make_company(db, seller_owner, tax_id="315000400")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900005401")
        buyer_co = make_company(db, buyer_owner, tax_id="315000401")
        db.commit()
        buyer_owner_id, buyer_co_id, offer_id = buyer_owner.id, buyer_co.id, offer.id

    body = {"company_id": buyer_co_id, "message": "hi"}
    for _ in range(10):
        assert (
            client.post(
                f"{_BASE}/market/{offer_id}/inquiries", json=body, headers=_auth(buyer_owner_id)
            ).status_code
            == 201
        )
    over = client.post(
        f"{_BASE}/market/{offer_id}/inquiries", json=body, headers=_auth(buyer_owner_id)
    )
    assert over.status_code == 429


@requires_real_db
def test_incoming_shows_approved_only(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005300")
        selling_co = make_company(db, seller_owner, tax_id="315000300")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900005301")
        buyer_co = make_company(db, buyer_owner, tax_id="315000301")
        from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
        from app.domains.marketplace.schemas import OfferRequestCreate  # noqa: PLC0415

        pending = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, OfferRequestCreate(quantity=None, message="pending"),
        )
        approved = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, OfferRequestCreate(quantity=None, message="approved"),
        )
        offer_request_service.moderate_offer_request(db, approved, staff_user_id=None, approve=True)
        db.commit()
        _ = pending
        seller_owner_id, selling_co_id = seller_owner.id, selling_co.id

    resp = client.get(
        f"{_BASE}/inquiries/incoming",
        params={"company_id": selling_co_id},
        headers=_auth(seller_owner_id),
    )
    assert resp.status_code == 200
    msgs = {i["message"] for i in resp.json()}
    assert msgs == {"approved"}  # pending inquiry stays internal to staff


@requires_real_db
def test_inquiry_rejected_when_offer_does_not_accept_rfq(api) -> None:  # noqa: ANN001
    """`accepts_rfq=False` is a seller's decision, so the server has to hold it.

    The portal hides the form, but a flag enforced only in one client is not
    enforced at all — the Mini App and a bare curl reach the same route.
    """
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005400")
        selling_co = make_company(db, seller_owner, tax_id="315000400")
        closed = make_seller_offer(db, company=selling_co, accepts_rfq=False)
        open_offer = make_seller_offer(db, company=selling_co, accepts_rfq=True)
        buyer_owner = make_account(db, "+998900005401")
        buyer_co = make_company(db, buyer_owner, tax_id="315000401")
        db.commit()
        buyer_owner_id, buyer_co_id = buyer_owner.id, buyer_co.id
        closed_id, open_id = closed.id, open_offer.id

    body = {"company_id": buyer_co_id, "quantity": "10.000", "message": "hello"}

    refused = client.post(
        f"{_BASE}/market/{closed_id}/inquiries", json=body, headers=_auth(buyer_owner_id)
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == {"code": "rfq_not_accepted"}

    allowed = client.post(
        f"{_BASE}/market/{open_id}/inquiries", json=body, headers=_auth(buyer_owner_id)
    )
    assert allowed.status_code == 201, allowed.text


@requires_real_db
def test_inquiry_records_the_offers_unit_and_currency(api) -> None:  # noqa: ANN001
    """The buyer types a bare number against an offer priced per KG in EUR.

    `qty_unit`/`currency` default to MT/None on the wire, so a client that omits
    them turns "500 KG" into "500 MT" for staff and the seller.
    """
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900005500")
        selling_co = make_company(db, seller_owner, tax_id="315000500")
        offer = make_seller_offer(db, company=selling_co, qty_unit="KG", currency="EUR")
        buyer_owner = make_account(db, "+998900005501")
        buyer_co = make_company(db, buyer_owner, tax_id="315000501")
        db.commit()
        buyer_owner_id, buyer_co_id, offer_id = buyer_owner.id, buyer_co.id, offer.id

    resp = client.post(
        f"{_BASE}/market/{offer_id}/inquiries",
        json={
            "company_id": buyer_co_id,
            "quantity": "500.000",
            "qty_unit": "KG",
            "target_price": "1.25",
            "currency": "EUR",
        },
        headers=_auth(buyer_owner_id),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["qty_unit"] == "KG"
    assert body["currency"] == "EUR"
