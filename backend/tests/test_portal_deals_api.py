"""Portal deal API tests (P2 W2 — T2.1 acceptance).

Route registration is DB-free. Behaviour runs against test_polymer (guarded)
with S3 stubbed. The point of this file is the authorization matrix — a Trade
Room holds both sides' commercial terms, so "who can see and do what" is the
security surface, not a detail:

  * a party's owner/manager acts; a plain member reads only,
  * a third company gets 404 (never 403 — existence must not leak),
  * the URL's company_id decides which hat you wear, even if you belong to both
    companies,
  * a supplier listing RFQ responses sees only their own price.
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_request,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_P = "/api/v1/portal"


def test_routes_registered() -> None:
    from app.domains.deals.api_portal import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    for path in (
        "/portal/companies/{company_id}/deals",
        "/portal/companies/{company_id}/deals/{deal_id}",
        "/portal/companies/{company_id}/deals/{deal_id}/transition",
        "/portal/companies/{company_id}/deals/{deal_id}/messages",
        "/portal/companies/{company_id}/deals/{deal_id}/documents",
        "/portal/companies/{company_id}/requests/{request_id}/responses",
    ):
        assert path in paths, f"{path} not registered"

    # The supplier RFQ list moved to the portal-market router in P5. Its full path
    # (/portal/market/requests) collides with that router's /{offer_id}, so it has to
    # be declared there, above the param route — previously it only resolved because
    # main.py happened to include the deals router first, which nothing recorded.
    from app.domains.marketplace.api_portal_market import router as market_router  # noqa: PLC0415

    assert "/portal/market/requests" not in paths
    market_paths = [r.path for r in market_router.routes]  # type: ignore[attr-defined]
    assert "/portal/market/requests" in market_paths
    assert market_paths.index("/portal/market/requests") < market_paths.index(
        "/portal/market/{offer_id}"
    ), "/requests must be declared before /{offer_id} or the param route swallows it"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    import hashlib  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()

    def fake_store(deal_id, section, content, filename):  # noqa: ANN001, ANN202
        mime = storage_service.validate_upload(content, filename)
        if mime not in storage_service.DEAL_FILE_MIMES:
            raise ValueError("invalid_file_type")
        return f"deals/{deal_id}/{section}/x-{filename}", mime, hashlib.sha256(content).hexdigest()

    monkeypatch.setattr(storage_service, "store_deal_file", fake_store)
    monkeypatch.setattr(
        storage_service, "presign_object", lambda key, ttl=600: f"http://s3.local/{key}?ttl={ttl}"
    )

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


# ── fixtures ──────────────────────────────────────────────────────────────────


def _account(session, phone):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    return account_id, {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _verified_company(session, account_id, tax):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole, CompanyStatus  # noqa: PLC0415

    with session() as db:
        account = db.get(UserAccount, account_id)
        company = company_service.create_company(db, account, "UZ", tax)
        # distributor+trader: buys and sells — the role gates (T-B) require it
        company_service.set_business_roles(
            db, company, [CompanyBusinessRole.distributor, CompanyBusinessRole.trader]
        )
        company.status = CompanyStatus.verified
        company.legal_name = f"OOO {tax}"
        db.commit()
        return company.id


def _scene(session):  # noqa: ANN001, ANN202
    """Buyer with an RFQ, seller with a response, and an accepted deal."""
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    buyer_id, buyer_h = _account(session, "+998900000001")
    seller_id, seller_h = _account(session, "+998900000002")
    buyer_co = _verified_company(session, buyer_id, "301111111")
    seller_co = _verified_company(session, seller_id, "302222222")

    with session() as db:
        buyer_acc = db.get(UserAccount, buyer_id)
        seller_acc = db.get(UserAccount, seller_id)
        request = make_request(db, company=db.get(Company, buyer_co), account=buyer_acc)
        response = RfqResponse(
            request_id=request.id,
            company_id=seller_co,
            created_by_user_account_id=seller_acc.id,
            price=decimal.Decimal("1250.00"),
            currency="USD",
            qty=decimal.Decimal("20"),
            qty_unit="MT",
        )
        db.add(response)
        db.flush()
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        db.commit()
        return {
            "buyer_h": buyer_h, "seller_h": seller_h,
            "buyer_id": buyer_id, "seller_id": seller_id,
            "buyer_co": buyer_co, "seller_co": seller_co,
            "deal_id": deal.id, "request_id": request.id, "response_id": response.id,
        }


_PDF = b"%PDF-1.4 fake invoice"


# ── listing + detail ──────────────────────────────────────────────────────────


@requires_real_db
def test_both_sides_see_the_deal_with_their_own_role(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)

    buyer_list = client.get(f"{_P}/companies/{s['buyer_co']}/deals", headers=s["buyer_h"])
    assert buyer_list.status_code == 200
    assert buyer_list.json()["items"][0]["role"] == "buyer"

    seller_list = client.get(f"{_P}/companies/{s['seller_co']}/deals", headers=s["seller_h"])
    assert seller_list.json()["items"][0]["role"] == "seller"


@requires_real_db
def test_detail_carries_both_parties_and_the_timeline(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    body = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}", headers=s["buyer_h"]
    ).json()

    assert body["status"] == "negotiation"
    assert body["buyer"]["company_id"] == s["buyer_co"]
    assert body["seller"]["company_id"] == s["seller_co"]
    assert body["seller"]["verified"] is True
    assert len(body["timeline"]) == 1
    assert body["escrow"] is None, "a deal in negotiation has no invoice yet"


@requires_real_db
def test_a_third_company_gets_404_not_403(api) -> None:  # noqa: ANN001
    """403 would confirm the deal exists. It must look like nothing is there."""
    client, session = api
    s = _scene(session)
    outsider_id, outsider_h = _account(session, "+998900000003")
    outsider_co = _verified_company(session, outsider_id, "303333333")

    assert client.get(
        f"{_P}/companies/{outsider_co}/deals/{s['deal_id']}", headers=outsider_h
    ).status_code == 404
    # Nor by borrowing a party's company id.
    assert client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}", headers=outsider_h
    ).status_code == 404


@requires_real_db
def test_anonymous_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    assert client.get(f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}").status_code == 401


# ── transitions ───────────────────────────────────────────────────────────────


@requires_real_db
def test_available_transitions_are_role_aware(api) -> None:  # noqa: ANN001
    """The action bar is built from this — a buyer must not be offered 'shipped'."""
    client, session = api
    s = _scene(session)

    buyer = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}", headers=s["buyer_h"]
    ).json()
    assert "cancelled" in buyer["available_transitions"]
    assert "contract_signed" not in buyer["available_transitions"]


@requires_real_db
def test_seller_ships_and_buyer_confirms_over_http(api) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    client, session = api
    s = _scene(session)
    with session() as db:
        deal = db.get(Deal, s["deal_id"])
        for status_ in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
        db.commit()

    ship = client.post(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "shipped"},
        headers=s["seller_h"],
    )
    assert ship.status_code == 200, ship.text
    assert ship.json()["status"] == "shipped"

    deliver = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "delivered"},
        headers=s["buyer_h"],
    )
    assert deliver.json()["status"] == "delivered"


@requires_real_db
def test_buyer_cannot_declare_a_shipment_over_http(api) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    client, session = api
    s = _scene(session)
    with session() as db:
        deal = db.get(Deal, s["deal_id"])
        for status_ in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
        db.commit()

    response = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "shipped"},
        headers=s["buyer_h"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "actor_not_allowed"


@requires_real_db
def test_a_party_cannot_forge_a_system_transition_over_http(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    response = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "contract_signed"},
        headers=s["buyer_h"],
    )
    assert response.status_code in (403, 409)


@requires_real_db
def test_cancel_without_a_reason_is_422(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    response = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "cancelled"},
        headers=s["buyer_h"],
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "reason_required"


@requires_real_db
def test_unknown_status_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    response = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "teleported"},
        headers=s["buyer_h"],
    )
    assert response.status_code == 422


# ── chat ──────────────────────────────────────────────────────────────────────


@requires_real_db
def test_chat_round_trip_and_mine_flag(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)

    posted = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": "Can you ship by Friday?"},
        headers=s["buyer_h"],
    )
    assert posted.status_code == 201, posted.text

    seller_view = client.get(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/messages", headers=s["seller_h"]
    ).json()
    assert seller_view["items"][0]["body"] == "Can you ship by Friday?"
    assert seller_view["items"][0]["mine"] is False, "the counterparty's message is not 'mine'"

    buyer_view = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages", headers=s["buyer_h"]
    ).json()
    assert buyer_view["items"][0]["mine"] is True


@requires_real_db
def test_chat_poll_is_incremental(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    first = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": "one"}, headers=s["buyer_h"],
    ).json()["id"]
    client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": "two"}, headers=s["buyer_h"],
    )

    page = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages?after_id={first}",
        headers=s["buyer_h"],
    ).json()
    assert [m["body"] for m in page["items"]] == ["two"]


@requires_real_db
def test_outsider_cannot_read_or_post_chat(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    outsider_id, outsider_h = _account(session, "+998900000003")
    outsider_co = _verified_company(session, outsider_id, "303333333")

    assert client.get(
        f"{_P}/companies/{outsider_co}/deals/{s['deal_id']}/messages", headers=outsider_h
    ).status_code == 404
    assert client.post(
        f"{_P}/companies/{outsider_co}/deals/{s['deal_id']}/messages",
        data={"body": "hello"}, headers=outsider_h,
    ).status_code == 404


@requires_real_db
def test_plain_member_reads_but_cannot_post(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from tests._verification_db import make_member  # noqa: PLC0415

    client, session = api
    s = _scene(session)
    junior_id, junior_h = _account(session, "+998900000004")
    with session() as db:
        make_member(db, db.get(Company, s["buyer_co"]), db.get(UserAccount, junior_id))
        db.commit()

    assert client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages", headers=junior_h
    ).status_code == 200
    denied = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": "hi"}, headers=junior_h,
    )
    assert denied.status_code == 403, "a viewer may follow the room, not speak for the company"


@requires_real_db
def test_empty_message_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    assert client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": "   "}, headers=s["buyer_h"],
    ).status_code == 422


@requires_real_db
def test_chat_file_round_trip(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    posted = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/messages",
        data={"body": ""},
        files={"file": ("spec.pdf", _PDF, "application/pdf")},
        headers=s["buyer_h"],
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["file_name"] == "spec.pdf"

    url = client.get(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}"
        f"/messages/{posted.json()['id']}/file",
        headers=s["seller_h"],
        follow_redirects=False,
    )
    assert url.status_code in (200, 307)


# ── documents ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_document_upload_and_presigned_read(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)

    uploaded = client.post(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/documents",
        data={"kind": "invoice"},
        files={"file": ("invoice.pdf", _PDF, "application/pdf")},
        headers=s["seller_h"],
    )
    assert uploaded.status_code == 201, uploaded.text
    doc_id = uploaded.json()["id"]

    link = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/documents/{doc_id}?as=url",
        headers=s["buyer_h"],
    )
    assert link.status_code == 200
    assert "ttl=600" in link.json()["url"], "presigned links are short-lived (<=600 s)"


@requires_real_db
def test_document_rejects_an_executable(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    response = client.post(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/documents",
        data={"kind": "other"},
        files={"file": ("payload.pdf", b"MZ\x90\x00 not a document", "application/pdf")},
        headers=s["seller_h"],
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_file_type"


@requires_real_db
def test_only_the_uploader_may_revoke_over_http(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    doc_id = client.post(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/documents",
        data={"kind": "invoice"},
        files={"file": ("invoice.pdf", _PDF, "application/pdf")},
        headers=s["seller_h"],
    ).json()["id"]

    assert client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/documents/{doc_id}/revoke",
        json={"reason": "not mine"}, headers=s["buyer_h"],
    ).status_code == 403

    ok = client.post(
        f"{_P}/companies/{s['seller_co']}/deals/{s['deal_id']}/documents/{doc_id}/revoke",
        json={"reason": "superseded"}, headers=s["seller_h"],
    )
    assert ok.status_code == 200
    assert ok.json()["revoked"] is True


# ── RFQ responses ─────────────────────────────────────────────────────────────


@requires_real_db
def test_supplier_responds_and_buyer_accepts(api) -> None:  # noqa: ANN001
    """The demo path: RFQ -> response -> accept -> Deal."""
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    client, session = api
    buyer_id, buyer_h = _account(session, "+998900000001")
    seller_id, seller_h = _account(session, "+998900000002")
    buyer_co = _verified_company(session, buyer_id, "301111111")
    seller_co = _verified_company(session, seller_id, "302222222")
    with session() as db:
        request = make_request(
            db, company=db.get(Company, buyer_co), account=db.get(UserAccount, buyer_id)
        )
        db.commit()
        request_id = request.id

    posted = client.post(
        f"{_P}/companies/{seller_co}/requests/{request_id}/responses",
        json={"price": "1250.00", "currency": "USD", "qty": "20", "qty_unit": "MT",
              "lead_time_days": 14, "comment": "ex-stock Tashkent"},
        headers=seller_h,
    )
    assert posted.status_code == 201, posted.text
    response_id = posted.json()["id"]

    accepted = client.post(
        f"{_P}/companies/{buyer_co}/requests/{request_id}/responses/{response_id}/accept",
        headers=buyer_h,
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["status"] == "negotiation"
    assert accepted.json()["amount"] == "25000.00"


@requires_real_db
def test_supplier_does_not_see_a_competitors_price(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    client, session = api
    buyer_id, buyer_h = _account(session, "+998900000001")
    a_id, a_h = _account(session, "+998900000002")
    b_id, b_h = _account(session, "+998900000003")
    buyer_co = _verified_company(session, buyer_id, "301111111")
    a_co = _verified_company(session, a_id, "302222222")
    b_co = _verified_company(session, b_id, "303333333")
    with session() as db:
        request = make_request(
            db, company=db.get(Company, buyer_co), account=db.get(UserAccount, buyer_id)
        )
        db.commit()
        request_id = request.id

    quote = {"price": "1250.00", "currency": "USD", "qty": "20", "qty_unit": "MT"}
    client.post(f"{_P}/companies/{a_co}/requests/{request_id}/responses", json=quote, headers=a_h)
    client.post(
        f"{_P}/companies/{b_co}/requests/{request_id}/responses",
        json={**quote, "price": "1190.00"}, headers=b_h,
    )

    buyer_sees = client.get(
        f"{_P}/companies/{buyer_co}/requests/{request_id}/responses", headers=buyer_h
    ).json()
    assert len(buyer_sees["items"]) == 2, "the RFQ owner compares every quote"

    a_sees = client.get(
        f"{_P}/companies/{a_co}/requests/{request_id}/responses", headers=a_h
    ).json()
    assert len(a_sees["items"]) == 1
    assert a_sees["items"][0]["company_id"] == a_co


@requires_real_db
def test_double_response_is_409(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    client, session = api
    buyer_id, _buyer_h = _account(session, "+998900000001")
    seller_id, seller_h = _account(session, "+998900000002")
    buyer_co = _verified_company(session, buyer_id, "301111111")
    seller_co = _verified_company(session, seller_id, "302222222")
    with session() as db:
        request = make_request(
            db, company=db.get(Company, buyer_co), account=db.get(UserAccount, buyer_id)
        )
        db.commit()
        request_id = request.id

    quote = {"price": "1250.00", "currency": "USD", "qty": "20", "qty_unit": "MT"}
    assert client.post(
        f"{_P}/companies/{seller_co}/requests/{request_id}/responses", json=quote, headers=seller_h
    ).status_code == 201
    dupe = client.post(
        f"{_P}/companies/{seller_co}/requests/{request_id}/responses", json=quote, headers=seller_h
    )
    assert dupe.status_code == 409
    assert dupe.json()["detail"] == "already_responded"


@requires_real_db
def test_only_the_rfq_owner_accepts(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    # The seller trying to accept their own quote must not find the RFQ at all.
    assert client.post(
        f"{_P}/companies/{s['seller_co']}/requests/{s['request_id']}"
        f"/responses/{s['response_id']}/accept",
        headers=s["seller_h"],
    ).status_code == 404


# ── supplier market list ──────────────────────────────────────────────────────


@requires_real_db
def test_market_rfq_list_is_anonymized(api) -> None:  # noqa: ANN001
    """Suppliers see the trade terms, never the buyer's contact details."""
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    client, session = api
    buyer_id, _bh = _account(session, "+998900000001")
    seller_id, seller_h = _account(session, "+998900000002")
    buyer_co = _verified_company(session, buyer_id, "301111111")
    seller_co = _verified_company(session, seller_id, "302222222")
    with session() as db:
        make_request(
            db,
            company=db.get(Company, buyer_co),
            account=db.get(UserAccount, buyer_id),
            contact_name="Ivan Petrov",
            phone="+998901234567",
            legal_address="Tashkent, Amir Temur 1",
        )
        db.commit()

    body = client.get(f"{_P}/market/requests?company_id={seller_co}", headers=seller_h).json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["product"] == "HDPE film"
    serialized = str(item)
    for secret in ("Ivan Petrov", "+998901234567", "Amir Temur"):
        assert secret not in serialized, f"{secret} leaked into the anonymized RFQ list"


@requires_real_db
def test_market_rfq_list_flags_my_existing_response(api) -> None:  # noqa: ANN001
    """So the UI shows 'Responded' instead of a button that 409s."""
    client, session = api
    s = _scene(session)
    body = client.get(
        f"{_P}/market/requests?company_id={s['seller_co']}", headers=s["seller_h"]
    ).json()
    assert body["items"] == [] or body["items"][0]["my_response_status"] == "accepted"


# ── escrow block (P3 T2.1) ────────────────────────────────────────────────────


def _open_escrow(session, deal_id):  # noqa: ANN001, ANN202
    """Walk the deal to contract_signed and raise its escrow, as the event would."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with session() as db:
        deal = db.get(Deal, deal_id)
        deal.amount = decimal.Decimal("25000.00")
        db.flush()
        for status_ in (DealStatus.contract_pending, DealStatus.contract_signed):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()
        return payment.id


@requires_real_db
def test_both_sides_see_the_same_escrow_block(api) -> None:  # noqa: ANN001
    """Payment status is not private between the parties — the whole point of
    escrow is that both can see where the money is."""
    client, session = api
    s = _scene(session)
    _open_escrow(session, s["deal_id"])

    for company_id, headers in (
        (s["buyer_co"], s["buyer_h"]),
        (s["seller_co"], s["seller_h"]),
    ):
        body = client.get(
            f"{_P}/companies/{company_id}/deals/{s['deal_id']}", headers=headers
        ).json()
        escrow = body["escrow"]
        assert escrow is not None
        assert escrow["status"] == "pending"
        assert escrow["amount"] == "25000.00", "money is a string on the wire"
        assert escrow["currency"] == "USD"
        assert escrow["funded_at"] is None
        assert escrow["released_at"] is None


@requires_real_db
def test_the_escrow_block_follows_the_payment(api) -> None:  # noqa: ANN001
    client, session = api
    s = _scene(session)
    payment_id = _open_escrow(session, s["deal_id"])

    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals.payment_models import EscrowPayment  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, "ops@example.com")
        escrow_service.mark(
            db, db.get(EscrowPayment, payment_id), EscrowStatus.funded,
            staff_user=staff, note="MT103 44821",
        )
        db.commit()

    body = client.get(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}", headers=s["buyer_h"]
    ).json()
    assert body["escrow"]["status"] == "funded"
    assert body["escrow"]["funded_at"] is not None
    assert body["status"] == "paid_escrow"


@requires_real_db
def test_the_parties_have_no_way_to_move_the_money(api) -> None:  # noqa: ANN001
    """Escrow is moved by the bank/operator alone. There must be no portal
    mutation at all — not a forbidden one, none."""
    from app.domains.deals.api_portal import router  # noqa: PLC0415

    for route in router.routes:  # type: ignore[attr-defined]
        assert "escrow" not in route.path, f"{route.path} exposes escrow to a party"

    client, session = api
    s = _scene(session)
    _open_escrow(session, s["deal_id"])
    # And the deal's own transition endpoint still refuses the money statuses.
    response = client.post(
        f"{_P}/companies/{s['buyer_co']}/deals/{s['deal_id']}/transition",
        json={"to_status": "paid_escrow"},
        headers=s["buyer_h"],
    )
    assert response.status_code in (403, 409)
