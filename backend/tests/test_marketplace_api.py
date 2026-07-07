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
