"""Portal market API tests (R2 W3 T3.1).

Route registration is DB-free. The rest run against test_polymer (guarded):
browse approved offers, single-offer detail with the caller company's inquiries,
cross-company isolation (member of A cannot read B's inquiry block), and a parity
contract test pinning the list card field-set to the webapp CatalogOfferOut.
"""

from __future__ import annotations

from datetime import UTC

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
    assert "/portal/market/companies/{company_id}" in paths
    assert "/portal/market/favorites" in paths


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


@requires_real_db
def test_detail_names_the_selling_company_for_the_contract_handoff(api) -> None:  # noqa: ANN001
    """«Запросить контракт» has to preselect the seller, so the detail names it.

    `display_name` cannot do that job: it is `short_name or legal_name`, while the
    counterparty directory searches `legal_name`/`tax_id` — a seller with a short
    name would never match. The id makes the handoff exact.
    """
    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900004300")
        selling_co = make_company(
            db,
            seller_owner,
            tax_id="314000300",
            legal_name='OOO "POLYMER TRADE"',
            short_name="PolyTrade",
        )
        offer = make_seller_offer(db, company=selling_co)
        buyer = make_account(db, "+998900004301")
        db.commit()
        buyer_id, offer_id, selling_co_id = buyer.id, offer.id, selling_co.id

    body = client.get(f"{_BASE}/{offer_id}", headers=_auth(buyer_id)).json()
    assert body["seller_company_id"] == selling_co_id
    assert body["seller_legal_name"] == 'OOO "POLYMER TRADE"'
    # The display name stays the short one — the two fields answer different questions.
    assert body["display_name"] == "PolyTrade"


@requires_real_db
def test_detail_has_no_selling_company_for_a_telegram_offer(api) -> None:  # noqa: ANN001
    """A TG-origin offer has no portal company, so there is nobody to contract with."""
    client, session = api
    with session() as db:
        seller = make_seller(db, telegram_user_id=770001, company_name="TG Trader")
        offer = make_seller_offer(db, seller=seller)
        buyer = make_account(db, "+998900004400")
        db.commit()
        buyer_id, offer_id = buyer.id, offer.id

    body = client.get(f"{_BASE}/{offer_id}", headers=_auth(buyer_id)).json()
    assert body["seller_company_id"] is None
    assert body["seller_legal_name"] is None


@requires_real_db
def test_public_company_profile_verified_only(api) -> None:  # noqa: ANN001
    """Strangers may read a verified seller; draft companies stay invisible."""
    from datetime import datetime  # noqa: PLC0415

    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        seller_owner = make_account(db, "+998900004500")
        verified = make_company(
            db,
            seller_owner,
            tax_id="314000500",
            legal_name="Химпром",
            short_name="Химпром",
            legal_address="Tashkent",
            legal_form="ООО",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 1, 15, tzinfo=UTC),
        )
        make_seller_offer(db, company=verified, grade_text="PP-PROFILE-A")
        make_seller_offer(db, company=verified, grade_text="PP-PROFILE-B")
        draft_owner = make_account(db, "+998900004501")
        draft = make_company(db, draft_owner, tax_id="314000501", legal_name="Draft Co")
        stranger = make_account(db, "+998900004502")
        db.commit()
        stranger_id, verified_id, draft_id = stranger.id, verified.id, draft.id

    ok = client.get(f"{_BASE}/companies/{verified_id}", headers=_auth(stranger_id))
    assert ok.status_code == 200
    body = ok.json()
    assert body["id"] == verified_id
    assert body["legal_name"] == "Химпром"
    assert body["legal_address"] == "Tashkent"
    assert body["offer_count"] == 2
    assert {o["grade_text"] for o in body["offers"]} == {"PP-PROFILE-A", "PP-PROFILE-B"}
    # Catalog-safe: never leak membership-only surfaces.
    assert "bank_accounts" not in body
    assert "documents" not in body
    assert "case" not in body
    assert "tax_id" not in body

    missing = client.get(f"{_BASE}/companies/{draft_id}", headers=_auth(stranger_id))
    assert missing.status_code == 404


@requires_real_db
def test_market_filter_by_seller_company(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        a_owner = make_account(db, "+998900004600")
        co_a = make_company(
            db, a_owner, tax_id="314000600", status=CompanyStatus.verified
        )
        make_seller_offer(db, company=co_a, grade_text="ONLY-A")
        b_owner = make_account(db, "+998900004601")
        co_b = make_company(
            db, b_owner, tax_id="314000601", status=CompanyStatus.verified
        )
        make_seller_offer(db, company=co_b, grade_text="ONLY-B")
        viewer = make_account(db, "+998900004602")
        db.commit()
        viewer_id, co_a_id = viewer.id, co_a.id

    resp = client.get(
        _BASE,
        params={"seller_company_id": co_a_id},
        headers=_auth(viewer_id),
    )
    assert resp.status_code == 200
    grades = {o["grade_text"] for o in resp.json()}
    assert grades == {"ONLY-A"}
