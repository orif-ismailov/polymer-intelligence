"""Dashboard dual-origin surface tests (R2 W4 T4.1) — real DB (guarded).

Covers the backend enablement for the origin badges:
  * dashboard /requests list carries origin + company_name for portal requests and
    the ?origin= filter partitions client vs company.
  * offer_request_service.to_admin_out no longer breaks on a portal inquiry (null
    client → buyer_company) or a company-origin offer (null seller → seller_company).
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller,
    make_seller_offer,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _staff_auth(staff_id: int) -> dict[str, str]:
    from app.core.security import create_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role='admin')}"}


@requires_real_db
def test_requests_list_origin_fields_and_filter(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        staff = make_staff(db, email="w4@example.com")
        owner = make_account(db, "+998900009001")
        company = make_company(db, owner, tax_id="317000001", short_name="Portal Co")
        from app.domains.requests import service as request_service  # noqa: PLC0415
        from app.domains.requests.webapp_schemas import RequestCreate  # noqa: PLC0415

        # one portal request, one TG request
        request_service.create_company_request(
            db, company, owner,
            RequestCreate(product_text="PP", grade_text="X", volume=decimal.Decimal("5")),
        )
        from app.domains.requests.models import Client, Request  # noqa: PLC0415
        from app.models.enums import RequestStatus  # noqa: PLC0415
        tg_client = Client(telegram_user_id=42, language="ru")
        db.add(tg_client)
        db.flush()
        db.add(Request(
            number="REQ-TG-1", client_id=tg_client.id, status=RequestStatus.new,
            product_text="LDPE", grade_text="Y",
            volume=decimal.Decimal("3"), volume_unit="MT",
        ))
        db.commit()
        staff_id = staff.id

    # full list: both origins present, portal row carries the company name
    rows = client.get("/api/v1/requests", headers=_staff_auth(staff_id)).json()
    by_origin = {r["origin"] for r in rows}
    assert by_origin == {"client", "company"}
    portal_row = next(r for r in rows if r["origin"] == "company")
    assert portal_row["company_name"] == "Portal Co"
    assert portal_row["company_id"] is not None

    # ?origin=company filters to the portal request only
    filtered = client.get(
        "/api/v1/requests", params={"origin": "company"}, headers=_staff_auth(staff_id)
    ).json()
    assert {r["origin"] for r in filtered} == {"company"}


@requires_real_db
def test_to_admin_out_handles_portal_and_company_parties(api) -> None:  # noqa: ANN001
    _client, session = api
    with session() as db:
        from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
        from app.domains.marketplace.schemas import OfferRequestCreate  # noqa: PLC0415

        # company-origin offer + portal buyer inquiry
        seller_owner = make_account(db, "+998900009100")
        selling_co = make_company(db, seller_owner, tax_id="317000100", short_name="Seller Co")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900009101")
        buyer_co = make_company(db, buyer_owner, tax_id="317000101", short_name="Buyer Co")
        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, OfferRequestCreate(quantity=None, message="hi"),
        )
        db.commit()

        out = offer_request_service.to_admin_out(req)
        assert out.origin == "company"
        assert out.buyer is None
        assert out.buyer_company is not None
        assert out.buyer_company.name == "Buyer Co"
        assert out.seller is None
        assert out.seller_company is not None
        assert out.seller_company.name == "Seller Co"


@requires_real_db
def test_to_admin_out_still_works_for_tg_parties(api) -> None:  # noqa: ANN001
    _client, session = api
    with session() as db:
        from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
        from app.domains.requests.models import Client  # noqa: PLC0415

        seller = make_seller(db, telegram_user_id=9001, company_name="TG Seller")
        offer = make_seller_offer(db, seller=seller)
        tg_buyer = Client(telegram_user_id=8001, company_name="TG Buyer", contact_name="Ivan")
        db.add(tg_buyer)
        db.flush()
        from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415
        from app.models.enums import OfferRequestStatus  # noqa: PLC0415
        req = OfferRequest(
            offer_id=offer.id, client_id=tg_buyer.id, qty_unit="MT",
            status=OfferRequestStatus.pending, message="hi",
        )
        db.add(req)
        db.flush()

        out = offer_request_service.to_admin_out(req)
        assert out.origin == "client"
        assert out.buyer is not None
        assert out.buyer.company_name == "TG Buyer"
        assert out.buyer_company is None
        assert out.seller is not None
        assert out.seller_company is None
