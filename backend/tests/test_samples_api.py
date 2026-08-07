"""
Sample-request API (P6 W3 — T3.2/T3.3).

Route registration runs DB-free; the rest is guarded on a localhost test_polymer.

What is worth an HTTP test rather than a service test: that each side sees only
its own column, that a request the caller is not party to is a 404 rather than a
403, that the buttons the API advertises are the caller's own, and that the sample
terms on the offer form refuse to describe a sample nobody can order.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_PORTAL = "/api/v1/portal"


def test_sample_routes_registered() -> None:
    from app.api.portal.samples import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/samples" in paths
    assert "/portal/market/offers/{offer_id}/samples" in paths
    assert "/portal/samples/{sample_id}/transition" in paths


def test_there_is_one_transition_door_not_five_verbs() -> None:
    """Five verb routes would be five places to forget the role check; the
    machine is a table and the API is one door."""
    from app.api.portal.samples import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert not any(
        verb in p for p in paths for verb in ("/accept", "/decline", "/receive")
    )


pytestmark_db = requires_real_db


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
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    from unittest.mock import patch  # noqa: PLC0415

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _scene(session, *, samples: bool = True):  # noqa: ANN001, ANN202
    """A verified seller with a sampleable approved offer, and a verified buyer."""
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from tests._verification_db import make_company, make_seller_offer  # noqa: PLC0415

    with session() as db:
        seller_owner = make_account(db, "+998900000501")
        buyer_owner = make_account(db, "+998900000502")
        # distributor+trader on the seller: it publishes offers (role gates, T-B)
        seller = make_company(
            db, seller_owner, tax_id="300000501", short_name="Продавец",
            roles=["distributor", "trader"],
        )
        buyer = make_company(db, buyer_owner, tax_id="300000502", short_name="Покупатель")
        seller.status = CompanyStatus.verified
        buyer.status = CompanyStatus.verified
        offer = make_seller_offer(
            db, company=seller, product_text="PP H030", samples_available=samples
        )
        db.commit()
        return {
            "seller_account": seller_owner.id,
            "seller_company": seller.id,
            "buyer_account": buyer_owner.id,
            "buyer_company": buyer.id,
            "offer_id": offer.id,
        }


def _request_sample(client, scene) -> dict:  # noqa: ANN001
    response = client.post(
        f"{_PORTAL}/market/offers/{scene['offer_id']}/samples",
        json={
            "company_id": scene["buyer_company"],
            "qty": "1 кг",
            "delivery_address": "Ташкент, Сергели 4",
        },
        headers=_auth(scene["buyer_account"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytestmark_db
class TestRequesting:
    def test_a_buyer_asks_and_sees_their_side(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        body = _request_sample(client, scene)

        assert body["status"] == "requested"
        assert body["my_role"] == "buyer"
        assert body["counterparty_name"] == "Продавец"
        # The buyer has nothing to do until the seller answers.
        assert body["available_transitions"] == []

    def test_an_offer_without_samples_is_refused(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session, samples=False)
        response = client.post(
            f"{_PORTAL}/market/offers/{scene['offer_id']}/samples",
            json={
                "company_id": scene["buyer_company"],
                "delivery_address": "Ташкент",
            },
            headers=_auth(scene["buyer_account"]),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "samples_not_available"

    def test_asking_for_your_own_sample_is_refused(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        response = client.post(
            f"{_PORTAL}/market/offers/{scene['offer_id']}/samples",
            json={
                "company_id": scene["seller_company"],
                "delivery_address": "Ташкент",
            },
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "own_offer"

    def test_a_second_live_request_is_409(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        _request_sample(client, scene)
        response = client.post(
            f"{_PORTAL}/market/offers/{scene['offer_id']}/samples",
            json={
                "company_id": scene["buyer_company"],
                "delivery_address": "Ташкент",
            },
            headers=_auth(scene["buyer_account"]),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "already_requested"

    def test_an_address_is_required(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        response = client.post(
            f"{_PORTAL}/market/offers/{scene['offer_id']}/samples",
            json={"company_id": scene["buyer_company"], "delivery_address": ""},
            headers=_auth(scene["buyer_account"]),
        )
        assert response.status_code == 422


@pytestmark_db
class TestTheTwoSides:
    def test_the_seller_sees_it_as_incoming_with_their_buttons(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        _request_sample(client, scene)

        incoming = client.get(
            f"{_PORTAL}/companies/{scene['seller_company']}/samples?side=incoming",
            headers=_auth(scene["seller_account"]),
        )
        assert incoming.status_code == 200
        card = incoming.json()[0]
        assert card["my_role"] == "seller"
        assert card["available_transitions"] == ["accepted", "declined"]
        assert card["counterparty_name"] == "Покупатель"

        # …and not as something they sent.
        sent = client.get(
            f"{_PORTAL}/companies/{scene['seller_company']}/samples?side=sent",
            headers=_auth(scene["seller_account"]),
        )
        assert sent.json() == []

    def test_the_round_trip(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        sample_id = _request_sample(client, scene)["id"]

        accepted = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": scene["seller_company"], "to_status": "accepted"},
            headers=_auth(scene["seller_account"]),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["available_transitions"] == ["sent"]

        shipped = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={
                "company_id": scene["seller_company"],
                "to_status": "sent",
                "courier": "BTS Express",
                "tracking_ref": "BTS-77123",
            },
            headers=_auth(scene["seller_account"]),
        )
        assert shipped.status_code == 200
        assert shipped.json()["tracking_ref"] == "BTS-77123"
        # Nothing left for the seller to do; it is the buyer's move now.
        assert shipped.json()["available_transitions"] == []

        received = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": scene["buyer_company"], "to_status": "received"},
            headers=_auth(scene["buyer_account"]),
        )
        assert received.status_code == 200
        assert received.json()["status"] == "received"

    def test_the_seller_cannot_confirm_the_delivery(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        sample_id = _request_sample(client, scene)["id"]
        for payload in (
            {"to_status": "accepted"},
            {"to_status": "sent", "courier": "BTS", "tracking_ref": "X1"},
        ):
            client.post(
                f"{_PORTAL}/samples/{sample_id}/transition",
                json={"company_id": scene["seller_company"], **payload},
                headers=_auth(scene["seller_account"]),
            )

        response = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": scene["seller_company"], "to_status": "received"},
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_your_move"

    def test_shipping_without_a_tracking_reference_is_refused(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        sample_id = _request_sample(client, scene)["id"]
        client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": scene["seller_company"], "to_status": "accepted"},
            headers=_auth(scene["seller_account"]),
        )
        response = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={
                "company_id": scene["seller_company"],
                "to_status": "sent",
                "courier": "BTS",
            },
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "shipment_details_required"

    def test_declining_needs_a_reason(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        sample_id = _request_sample(client, scene)["id"]
        response = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": scene["seller_company"], "to_status": "declined"},
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "reason_required"

    def test_an_outsider_gets_a_404_not_a_403(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        sample_id = _request_sample(client, scene)["id"]

        from app.models.enums import CompanyStatus  # noqa: PLC0415
        from tests._verification_db import make_company  # noqa: PLC0415

        with session() as db:
            outsider = make_account(db, "+998900000503")
            company = make_company(db, outsider, tax_id="300000503")
            company.status = CompanyStatus.verified
            db.commit()
            outsider_id, company_id = outsider.id, company.id

        response = client.post(
            f"{_PORTAL}/samples/{sample_id}/transition",
            json={"company_id": company_id, "to_status": "accepted"},
            headers=_auth(outsider_id),
        )
        assert response.status_code == 404


@pytestmark_db
class TestOfferSampleTerms:
    def test_a_seller_publishes_sample_terms(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        response = client.post(
            f"{_PORTAL}/companies/{scene['seller_company']}/offers",
            json={
                "product_text": "PP H030",
                "samples_available": True,
                "sample_price": "15.00",
                "sample_dispatch_days": 3,
            },
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["samples_available"] is True
        assert body["sample_dispatch_days"] == 3
        # Uploading nothing: no passport, no independent verification.
        assert body["has_lab_passport"] is False
        assert body["lab_verified"] is False

    def test_sample_terms_without_samples_are_refused(self, api) -> None:  # noqa: ANN001
        """Otherwise the card promises a price for something nobody can order."""
        client, session = api
        scene = _scene(session)
        response = client.post(
            f"{_PORTAL}/companies/{scene['seller_company']}/offers",
            json={
                "product_text": "PP H030",
                "samples_available": False,
                "sample_price": "15.00",
            },
            headers=_auth(scene["seller_account"]),
        )
        assert response.status_code == 422
