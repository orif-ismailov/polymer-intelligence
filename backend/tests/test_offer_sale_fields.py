"""
Offer sale fields + favorites through the stack (P4 W1 — T1.2).

Schema validation is DB-free; the favorites API runs against test_polymer
(guarded).

The one NEW rule is that a made-to-order offer must say how long it takes: an
offer with no price AND no lead time tells a buyer nothing they can act on. The
availability/pricing rules the plan also listed ALREADY exist on the webapp
schema (`SellerOfferCreate._availability_pricing`), so this file pins the current
behaviour rather than re-tightening it — see the parity test below.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_seller,
    make_seller_offer,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_P = "/api/v1/portal"


# ── schema rules (no DB) ──────────────────────────────────────────────────────


class TestMadeToOrderNeedsALeadTime:
    def test_on_order_without_a_lead_time_is_rejected(self) -> None:
        """A made-to-order offer carries no price ("по запросу"). With no lead
        time either, the card says nothing a buyer can plan around."""
        import pydantic  # noqa: PLC0415

        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        with pytest.raises(pydantic.ValidationError, match="lead_time_days"):
            CompanyOfferIn(
                product_text="HDPE film",
                availability=OfferAvailability.on_order,
            )

    def test_on_order_with_a_lead_time_is_accepted(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        body = CompanyOfferIn(
            product_text="HDPE film",
            availability=OfferAvailability.on_order,
            lead_time_days=21,
        )
        assert body.lead_time_days == 21
        assert body.price is None, "a made-to-order offer is priced on request"

    def test_in_stock_needs_no_lead_time(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        body = CompanyOfferIn(
            product_text="HDPE film",
            availability=OfferAvailability.in_stock,
            qty_available="20",
            price="1250.00",
        )
        assert body.lead_time_days is None

    def test_a_negative_lead_time_is_rejected(self) -> None:
        import pydantic  # noqa: PLC0415

        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        with pytest.raises(pydantic.ValidationError):
            CompanyOfferIn(
                product_text="HDPE film",
                availability=OfferAvailability.on_order,
                lead_time_days=-1,
            )


class TestExistingRulesAreNotRetightened:
    def test_the_webapp_schema_still_owns_its_own_availability_rule(self) -> None:
        """`SellerOfferCreate` (the FROZEN Mini App surface) already forces
        qty/price to null for on_order and requires them for in_stock. It must
        NOT gain the lead-time requirement: the frozen client cannot send the
        field, so requiring it would break offer creation from Telegram."""
        from app.domains.marketplace.schemas import SellerOfferCreate  # noqa: PLC0415
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        body = SellerOfferCreate(
            product_text="HDPE film", availability=OfferAvailability.on_order
        )
        assert body.price is None
        assert body.qty_available is None

    def test_readiness_flags_default_to_rfq_only(self) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415

        body = CompanyOfferIn(product_text="HDPE film", qty_available="1", price="1")
        assert body.accepts_rfq is True
        assert body.accepts_contract is False
        assert body.accepts_escrow is False


class TestMarketCardCarriesTheNewFields:
    def test_portal_card_is_a_superset_of_the_webapp_contract(self) -> None:
        """The Mini App card contract stays byte-identical (webapp/ is frozen);
        the portal card extends it, so P4's badges never drift the shared shape."""
        from app.domains.marketplace.portal_market_schemas import (
            PortalMarketOfferOut,  # noqa: PLC0415
        )
        from app.domains.marketplace.schemas import CatalogOfferOut  # noqa: PLC0415

        webapp = set(CatalogOfferOut.model_fields)
        portal = set(PortalMarketOfferOut.model_fields)
        assert webapp < portal, "the portal card must EXTEND the webapp contract"
        assert {
            "lead_time_days",
            "sale_mode",
            "accepts_rfq",
            "accepts_contract",
            "accepts_escrow",
            "is_favorite",
            "manufacturer",
            "key_properties",
            "applications",
            "cas_number",
            "hs_code",
        } <= portal


# ── favorites API (real DB) ───────────────────────────────────────────────────


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


def _account(session, phone):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    return account_id, {
        "Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"
    }


def _approved_offer(session):  # noqa: ANN001, ANN202
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    with session() as db:
        seller = make_seller(db, telegram_user_id=555001)
        offer = make_seller_offer(db, seller=seller, status=SellerOfferStatus.approved)
        offer.published_at = utcnow()
        db.commit()
        return offer.id


def test_favorite_routes_registered() -> None:
    from app.domains.marketplace.api_portal_market import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/market/offers/{offer_id}/favorite" in paths
    assert "/portal/market/favorites" in paths


@requires_real_db
def test_star_unstar_round_trip(api) -> None:  # noqa: ANN001
    client, session = api
    _account_id, headers = _account(session, "+998900000001")
    offer_id = _approved_offer(session)

    assert client.get(f"{_P}/market/favorites", headers=headers).json() == []

    assert client.post(f"{_P}/market/offers/{offer_id}/favorite", headers=headers).status_code == 201
    listed = client.get(f"{_P}/market/favorites", headers=headers).json()
    assert [o["id"] for o in listed] == [offer_id]
    assert listed[0]["is_favorite"] is True

    assert client.delete(f"{_P}/market/offers/{offer_id}/favorite", headers=headers).status_code == 204
    assert client.get(f"{_P}/market/favorites", headers=headers).json() == []


@requires_real_db
def test_starring_twice_is_not_an_error(api) -> None:  # noqa: ANN001
    """A double tap on the heart (or a retried request) must not 500 on the
    unique constraint — the second star is simply already true."""
    client, session = api
    _account_id, headers = _account(session, "+998900000001")
    offer_id = _approved_offer(session)

    first = client.post(f"{_P}/market/offers/{offer_id}/favorite", headers=headers)
    second = client.post(f"{_P}/market/offers/{offer_id}/favorite", headers=headers)
    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert len(client.get(f"{_P}/market/favorites", headers=headers).json()) == 1


@requires_real_db
def test_unstarring_something_never_starred_is_a_no_op(api) -> None:  # noqa: ANN001
    client, session = api
    _account_id, headers = _account(session, "+998900000001")
    offer_id = _approved_offer(session)
    assert client.delete(f"{_P}/market/offers/{offer_id}/favorite", headers=headers).status_code == 204


@requires_real_db
def test_a_shortlist_is_personal(api) -> None:  # noqa: ANN001
    """Two accounts, one offer: each sees only their own star."""
    client, session = api
    _a, headers_a = _account(session, "+998900000001")
    _b, headers_b = _account(session, "+998900000002")
    offer_id = _approved_offer(session)

    client.post(f"{_P}/market/offers/{offer_id}/favorite", headers=headers_a)
    assert len(client.get(f"{_P}/market/favorites", headers=headers_a).json()) == 1
    assert client.get(f"{_P}/market/favorites", headers=headers_b).json() == []


@requires_real_db
def test_the_market_list_flags_what_this_account_starred(api) -> None:  # noqa: ANN001
    """So the heart renders filled on first paint instead of after a second call."""
    client, session = api
    _account_id, headers = _account(session, "+998900000001")
    offer_id = _approved_offer(session)

    before = client.get(f"{_P}/market", headers=headers).json()
    assert before[0]["is_favorite"] is False

    client.post(f"{_P}/market/offers/{offer_id}/favorite", headers=headers)
    after = client.get(f"{_P}/market", headers=headers).json()
    assert after[0]["is_favorite"] is True
    assert after[0]["accepts_rfq"] is True, "the readiness flags ride on the card too"


@requires_real_db
def test_starring_an_unapproved_offer_is_refused(api) -> None:  # noqa: ANN001
    """The heart only exists on the public catalog; a draft is not there to star."""
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    client, session = api
    _account_id, headers = _account(session, "+998900000001")
    with session() as db:
        seller = make_seller(db, telegram_user_id=555002)
        offer = make_seller_offer(db, seller=seller, status=SellerOfferStatus.draft)
        db.commit()
        draft_id = offer.id

    assert client.post(f"{_P}/market/offers/{draft_id}/favorite", headers=headers).status_code == 404


@requires_real_db
def test_favorites_require_an_account(api) -> None:  # noqa: ANN001
    client, session = api
    offer_id = _approved_offer(session)
    assert client.get(f"{_P}/market/favorites").status_code == 401
    assert client.post(f"{_P}/market/offers/{offer_id}/favorite").status_code == 401
