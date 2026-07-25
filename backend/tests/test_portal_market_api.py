"""Portal market API tests (R2 W3 T3.1).

Route registration is DB-free. The rest run against test_polymer (guarded):
browse approved offers, single-offer detail with the caller company's inquiries,
cross-company isolation (member of A cannot read B's inquiry block), and a parity
contract test pinning the list card field-set to the webapp CatalogOfferOut.
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

_BASE = "/api/v1/portal/market"


def test_market_routes_registered() -> None:
    from app.api.portal.market import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/market" in paths
    assert "/portal/market/{offer_id}" in paths


def test_list_card_fields_match_webapp_catalog_contract() -> None:
    """Parity: the portal list serializer IS the webapp CatalogOfferOut — the field
    set must not drift from the Mini App market card."""
    from app.schemas.marketplace import CatalogOfferOut  # noqa: PLC0415

    fields = set(CatalogOfferOut.model_fields)
    expected = {
        "id", "product_id", "product_text", "grade_text", "polymer_type",
        "availability", "qty_available", "qty_unit", "price", "currency",
        "incoterms", "warehouse_city", "country", "min_order_qty", "description",
        "published_at", "files", "origin", "display_name", "company_verified",
        "seller", "is_own",
    }
    assert fields == expected, f"CatalogOfferOut field drift: {fields ^ expected}"


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


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
def test_browse_lists_approved_offers(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900004001")
        selling_co = make_company(db, seller_owner, tax_id="314000001")
        make_seller_offer(db, company=selling_co, grade_text="APPROVED-A")
        # a non-approved offer must not appear
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415
        make_seller_offer(
            db, company=selling_co, grade_text="DRAFT-B", status=SellerOfferStatus.draft
        )
        buyer = make_account(db, "+998900004002")
        db.commit()
        buyer_id = buyer.id

    resp = client.get(_BASE, headers=_auth(buyer_id))
    assert resp.status_code == 200
    grades = {o["grade_text"] for o in resp.json()}
    assert "APPROVED-A" in grades
    assert "DRAFT-B" not in grades


@requires_real_db
def test_detail_includes_my_company_inquiries(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900004100")
        selling_co = make_company(db, seller_owner, tax_id="314000100")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900004101")
        buyer_co = make_company(db, buyer_owner, tax_id="314000101")
        from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415
        from app.services import offer_request_service  # noqa: PLC0415
        offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer,
            OfferRequestCreate(quantity=None, message="hi"),
        )
        db.commit()
        buyer_owner_id, buyer_co_id, offer_id = buyer_owner.id, buyer_co.id, offer.id

    resp = client.get(
        f"{_BASE}/{offer_id}",
        params={"company_id": buyer_co_id},
        headers=_auth(buyer_owner_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == offer_id
    assert len(body["my_inquiries"]) == 1
    assert body["my_inquiries"][0]["message"] == "hi"


@requires_real_db
def test_detail_company_scope_isolation(api) -> None:  # noqa: ANN001
    """A member of company A cannot pass company B's id (non-member → 404)."""
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900004200")
        selling_co = make_company(db, seller_owner, tax_id="314000200")
        offer = make_seller_offer(db, company=selling_co)
        a_owner = make_account(db, "+998900004201")
        make_company(db, a_owner, tax_id="314000201")
        b_owner = make_account(db, "+998900004202")
        company_b = make_company(db, b_owner, tax_id="314000202")
        db.commit()
        a_owner_id, company_b_id, offer_id = a_owner.id, company_b.id, offer.id

    resp = client.get(
        f"{_BASE}/{offer_id}",
        params={"company_id": company_b_id},
        headers=_auth(a_owner_id),  # A acting, claims B → 404
    )
    assert resp.status_code == 404
