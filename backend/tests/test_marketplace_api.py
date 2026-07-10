"""
Tests for the Phase 2 marketplace API: seller offers, public catalog, moderation.

Fully mocked (MagicMock db + dependency overrides), mirroring test_webapp_requests_api.
Security invariants checked: initData required for the webapp surface; the catalog
detail 404s for a non-approved/missing offer; moderation requires staff auth.
"""

from __future__ import annotations

import datetime
import decimal
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _mock_client(id: int = 1, telegram_user_id: int = 555) -> MagicMock:
    c = MagicMock()
    c.id = id
    c.telegram_user_id = telegram_user_id
    c.language = "ru"
    return c


def _mock_seller(id: int = 7) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.company_name = "Chem Trade LLC"
    s.contact_name = "Ivanov"
    s.phone = "+998 90 123 45 67"
    s.telegram_username = "chem_trade"
    s.is_verified = True
    return s


def _mock_offer(id: int = 11, status: str = "approved") -> MagicMock:
    from app.models.enums import OfferAvailability, PriceBasis, SellerOfferStatus  # noqa: PLC0415

    o = MagicMock()
    o.id = id
    o.status = SellerOfferStatus(status)
    o.product_id = 2
    o.product_text = None
    o.grade_text = "HDPE 5502"
    o.polymer_type = "HDPE"
    o.availability = OfferAvailability.in_stock
    o.qty_available = decimal.Decimal("100")
    o.qty_unit = "MT"
    o.price = decimal.Decimal("1200")
    o.currency = "USD"
    o.incoterms = PriceBasis.FCA
    o.warehouse_city = "Tashkent"
    o.country = "UZ"
    o.min_order_qty = decimal.Decimal("20")
    o.description = "HDPE for extrusion"
    o.moderation_note = None
    o.files = []
    o.published_at = datetime.datetime(2026, 6, 20, tzinfo=datetime.UTC)
    o.created_at = datetime.datetime(2026, 6, 19, tzinfo=datetime.UTC)
    o.seller = _mock_seller()
    return o


def _app_with_client(mock_db: MagicMock) -> Any:
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _override_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_db
    application.dependency_overrides[get_current_client] = _mock_client
    return application


@pytest.fixture
def market_client() -> Generator[TestClient, None, None]:
    mock_db = MagicMock()
    application = _app_with_client(mock_db)
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as tc:
        yield tc


# ── Public catalog ────────────────────────────────────────────────────────────

class TestCatalog:
    def test_list_offers_200(self, market_client: TestClient):
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.list_catalog.return_value = [_mock_offer()]
            resp = market_client.get("/api/v1/webapp/market/offers")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data[0]["id"] == 11
        assert data[0]["seller"]["company_name"] == "Chem Trade LLC"

    def test_offer_detail_404_when_not_approved(self, market_client: TestClient):
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.get_catalog_offer.return_value = None
            resp = market_client.get("/api/v1/webapp/market/offers/999")
        assert resp.status_code == 404, resp.text

    def test_categories_200(self, market_client: TestClient):
        from app.schemas.marketplace import CategoryCount  # noqa: PLC0415

        with patch("app.api.webapp.market.offer_service") as svc:
            svc.category_counts.return_value = [CategoryCount(code="HDPE", count=3)]
            resp = market_client.get("/api/v1/webapp/market/categories")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0] == {"code": "HDPE", "count": 3}

    def test_catalog_requires_initdata(self):
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            application, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/webapp/market/offers")
        assert resp.status_code == 401, resp.text

    def test_list_offers_excludes_own_seller(self, market_client: TestClient):
        """The caller's own listings are filtered out of the catalog they browse."""
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.seller_id_for.return_value = 7
            svc.list_catalog.return_value = []
            resp = market_client.get("/api/v1/webapp/market/offers")
        assert resp.status_code == 200, resp.text
        assert svc.list_catalog.call_args.kwargs["exclude_seller_id"] == 7

    def test_categories_exclude_own_seller(self, market_client: TestClient):
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.seller_id_for.return_value = 7
            svc.category_counts.return_value = []
            resp = market_client.get("/api/v1/webapp/market/categories")
        assert resp.status_code == 200, resp.text
        assert svc.category_counts.call_args.kwargs["exclude_seller_id"] == 7

    def test_offer_detail_sets_is_own_for_owner(self, market_client: TestClient):
        offer = _mock_offer(status="approved")
        offer.seller_id = 7
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.get_catalog_offer.return_value = offer
            svc.seller_id_for.return_value = 7  # caller owns seller 7
            resp = market_client.get("/api/v1/webapp/market/offers/11")
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_own"] is True

    def test_offer_detail_is_own_false_for_others(self, market_client: TestClient):
        offer = _mock_offer(status="approved")
        offer.seller_id = 7
        with patch("app.api.webapp.market.offer_service") as svc:
            svc.get_catalog_offer.return_value = offer
            svc.seller_id_for.return_value = 999  # someone else
            resp = market_client.get("/api/v1/webapp/market/offers/11")
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_own"] is False


# ── Seller offers ──────────────────────────────────────────────────────────────

class TestSellerOffers:
    def test_create_offer_201(self, market_client: TestClient):
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_or_create_seller.return_value = _mock_seller()
            svc.create_offer.return_value = _mock_offer(status="pending_moderation")
            resp = market_client.post(
                "/api/v1/webapp/seller/offers",
                json={
                    "product_id": 2,
                    "grade_text": "HDPE 5502",
                    "qty_available": "100",
                    "price": "1200",
                    "currency": "USD",
                    "company_name": "Chem Trade LLC",
                    "phone": "+998901234567",
                },
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "pending_moderation"
        # Read side surfaces availability; the mock offer defaults to in_stock.
        assert body["availability"] == "in_stock"

    def test_create_offer_availability_defaults_in_stock(self, market_client: TestClient):
        """Omitting availability parses to the in_stock default in the create schema."""
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_or_create_seller.return_value = _mock_seller()
            svc.create_offer.return_value = _mock_offer(status="pending_moderation")
            resp = market_client.post(
                "/api/v1/webapp/seller/offers",
                json={"product_id": 2, "qty_available": "100", "price": "1200"},
            )
        assert resp.status_code == 201, resp.text
        # data is the 3rd positional arg of create_offer(db, seller, data)
        data = svc.create_offer.call_args.args[2]
        assert data.availability == OfferAvailability.in_stock

    def test_create_offer_availability_on_order(self, market_client: TestClient):
        """availability='on_order' is accepted and forwarded to the service verbatim."""
        from app.models.enums import OfferAvailability  # noqa: PLC0415

        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_or_create_seller.return_value = _mock_seller()
            svc.create_offer.return_value = _mock_offer(status="pending_moderation")
            resp = market_client.post(
                "/api/v1/webapp/seller/offers",
                json={
                    "product_id": 2,
                    "availability": "on_order",
                    "qty_available": "100",
                    "price": "1200",
                },
            )
        assert resp.status_code == 201, resp.text
        data = svc.create_offer.call_args.args[2]
        assert data.availability == OfferAvailability.on_order

    def test_create_offer_invalid_availability_422(self, market_client: TestClient):
        resp = market_client.post(
            "/api/v1/webapp/seller/offers",
            json={
                "product_id": 2,
                "availability": "maybe",
                "qty_available": "100",
                "price": "1200",
            },
        )
        assert resp.status_code == 422, resp.text

    def test_create_offer_missing_product_422(self, market_client: TestClient):
        resp = market_client.post(
            "/api/v1/webapp/seller/offers",
            json={"qty_available": "100", "price": "1200"},
        )
        assert resp.status_code == 422, resp.text

    def test_create_offer_zero_price_422(self, market_client: TestClient):
        resp = market_client.post(
            "/api/v1/webapp/seller/offers",
            json={"product_id": 2, "qty_available": "100", "price": "0"},
        )
        assert resp.status_code == 422, resp.text


# ── Moderation (staff only) ─────────────────────────────────────────────────────

class TestModeration:
    def test_queue_requires_staff_auth(self):
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            application, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/admin/moderation/offers")
        assert resp.status_code == 401, resp.text

    def test_approve_offer_200(self):
        from app.api.deps import require_analyst_or_admin  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        staff = MagicMock()
        staff.id = 3
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = _mock_offer(status="pending_moderation")
        mock_db.query.return_value = mock_query

        def _db() -> Generator[Any, None, None]:
            yield mock_db

        application = create_app()
        application.dependency_overrides[get_db] = _db
        application.dependency_overrides[require_analyst_or_admin] = lambda: staff

        # Let the real moderate_offer run against the mock offer (it mutates status →
        # approved + stamps published_at, then write_audit/flush on the mock db).
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as tc:
            resp = tc.post("/api/v1/admin/moderation/offers/11/approve", json={"note": "ok"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"


# ── Buyer edits their own inquiry (PATCH /webapp/market/my-requests/{id}) ───────


def _mock_own_inquiry(client_id: int = 1) -> MagicMock:
    """An OfferRequest stand-in that serialises as OfferRequestOut (buyer=client 1)."""
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    offer = MagicMock()
    offer.id = 2
    offer.product_id = None
    offer.product_text = "EVA"
    offer.grade_text = "A"
    offer.price = decimal.Decimal("1200")
    offer.currency = "USD"
    offer.qty_unit = "MT"

    o = MagicMock()
    o.id = 5
    o.client_id = client_id
    o.offer_id = 2
    o.status = OfferRequestStatus.pending
    o.quantity = decimal.Decimal("20")
    o.qty_unit = "MT"
    o.target_price = None
    o.currency = None
    o.message = None
    o.created_at = datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC)
    o.edited_at = None
    o.offer = offer
    return o


class TestEditInquiry:
    def test_patch_foreign_inquiry_404(self, market_client: TestClient):
        """A buyer cannot edit an inquiry that isn't theirs (IDOR → 404)."""
        with patch("app.api.webapp.market.offer_request_service") as svc:
            svc.get_offer_request.return_value = _mock_own_inquiry(client_id=999)
            resp = market_client.patch(
                "/api/v1/webapp/market/my-requests/5", json={"quantity": "10"}
            )
        assert resp.status_code == 404, resp.text
        svc.update_offer_request.assert_not_called()

    def test_patch_own_inquiry_200_and_reposts(self, market_client: TestClient):
        """Editing one's own inquiry returns 200 and re-posts to the team group."""
        own = _mock_own_inquiry(client_id=1)  # market_client's caller is id=1
        with patch("app.api.webapp.market.offer_request_service") as svc:
            svc.get_offer_request.return_value = own
            svc.update_offer_request.return_value = (
                own,
                [{"field": "quantity", "old": "20 MT", "new": "40 MT"}],
            )
            resp = market_client.patch(
                "/api/v1/webapp/market/my-requests/5", json={"quantity": "40"}
            )
        assert resp.status_code == 200, resp.text
        svc.enqueue_offer_request_to_group.assert_called_once_with(5)

    def test_patch_missing_inquiry_404(self, market_client: TestClient):
        with patch("app.api.webapp.market.offer_request_service") as svc:
            svc.get_offer_request.return_value = None
            resp = market_client.patch(
                "/api/v1/webapp/market/my-requests/999", json={"message": "hi"}
            )
        assert resp.status_code == 404, resp.text


# ── Seller edits their own offer (GET/PATCH /webapp/seller/offers/{id}) ─────────


class TestSellerOfferEdit:
    _BODY = {"product_id": 2, "qty_available": "150", "price": "1300"}

    def test_get_own_offer_200(self, market_client: TestClient):
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = _mock_offer(status="approved")
            resp = market_client.get("/api/v1/webapp/seller/offers/11")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == 11

    def test_get_absent_offer_404(self, market_client: TestClient):
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = None  # not the caller's / doesn't exist
            resp = market_client.get("/api/v1/webapp/seller/offers/999")
        assert resp.status_code == 404, resp.text

    def test_patch_own_offer_200_requeues_group(self, market_client: TestClient):
        """Editing a public offer re-enters moderation → re-posts to the team group."""
        offer = _mock_offer(status="pending_moderation")
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = offer
            svc.update_offer.return_value = (offer, True)  # requeued
            resp = market_client.patch("/api/v1/webapp/seller/offers/11", json=self._BODY)
        assert resp.status_code == 200, resp.text
        svc.update_offer.assert_called_once()
        svc.enqueue_offer_group_notify.assert_called_once_with(11, edited=True)

    def test_patch_own_offer_no_requeue_skips_group(self, market_client: TestClient):
        """Editing a draft/pending offer stays in place → no group re-notify."""
        offer = _mock_offer(status="pending_moderation")
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = offer
            svc.update_offer.return_value = (offer, False)
            resp = market_client.patch("/api/v1/webapp/seller/offers/11", json=self._BODY)
        assert resp.status_code == 200, resp.text
        svc.enqueue_offer_group_notify.assert_not_called()

    def test_patch_absent_offer_404(self, market_client: TestClient):
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = None
            resp = market_client.patch("/api/v1/webapp/seller/offers/999", json=self._BODY)
        assert resp.status_code == 404, resp.text
        svc.update_offer.assert_not_called()

    def test_patch_invalid_body_422(self, market_client: TestClient):
        """Full-replacement validation still applies (price must be > 0)."""
        with patch("app.api.webapp.seller.offer_service") as svc:
            svc.get_own_offer.return_value = _mock_offer(status="approved")
            resp = market_client.patch(
                "/api/v1/webapp/seller/offers/11",
                json={"product_id": 2, "qty_available": "150", "price": "0"},
            )
        assert resp.status_code == 422, resp.text
