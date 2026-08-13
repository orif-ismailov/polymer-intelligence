"""
Phase 4 tests: the sourcing waterfall priority + the AI broker API (mocked).

run_sourcing's ranking is pure logic over ORM rows, so it is exercised with light
fakes; the API tests use dependency overrides like the other API suites.
"""

from __future__ import annotations

import decimal
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# ── Waterfall priority (pure-ish) ───────────────────────────────────────────────

class TestWaterfall:
    def test_recommended_prefers_inventory_over_cheaper_marketplace(self):
        from app.models.enums import SellerOfferStatus
        from app.services import sourcing_service

        # Inventory at 1200, a cheaper marketplace offer at 1000. Priority wins:
        # inventory (priority 1) must be recommended despite the higher price.
        inv = SimpleNamespace(
            grade_text="HDPE 5502", cost_price=decimal.Decimal("1200"), currency="USD",
            qty_on_hand=decimal.Decimal("50"), warehouse_city="Tashkent", product_id=2,
        )
        offer = SimpleNamespace(
            price=decimal.Decimal("1000"), currency="USD", qty_available=decimal.Decimal("100"),
            warehouse_city="Tashkent", status=SellerOfferStatus.approved,
            seller=SimpleNamespace(company_name="Chem Trade LLC"),
        )

        db = MagicMock()

        # Each db.query(Model) returns an object whose filter/all yields the right rows.
        def _query(model: Any):
            from app.domains.marketplace.models import SellerOffer
            from app.models.sourcing import InventoryItem, PartnerSupplier

            q = MagicMock()
            q.filter.return_value = q
            if model is InventoryItem:
                q.all.return_value = [inv]
            elif model is PartnerSupplier:
                q.all.return_value = []
            elif model is SellerOffer:
                q.all.return_value = [offer]
            else:
                q.all.return_value = []
            return q

        db.query.side_effect = _query
        # No foreign price points / market context.
        db.execute.return_value.mappings.return_value.one.return_value = {"avg_price": None}
        db.execute.return_value.mappings.return_value.all.return_value = []

        request = SimpleNamespace(
            product_id=2, product_text=None, grade_text="HDPE 5502",
            volume=decimal.Decimal("100"), volume_unit="MT",
            target_price=decimal.Decimal("1050"), currency="USD",
        )

        result = sourcing_service.run_sourcing(db, request)  # type: ignore[arg-type]
        assert len(result["options"]) == 2
        assert result["recommended"]["source"] == "inventory"
        sources = {o["source"] for o in result["options"]}
        assert sources == {"inventory", "marketplace"}


# ── API (mocked) ─────────────────────────────────────────────────────────────────

def _staff_app(mock_db: MagicMock) -> Any:
    from app.api.deps import require_analyst_or_admin
    from app.core.db import get_db
    from app.main import create_app

    def _db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[require_analyst_or_admin] = lambda: MagicMock(id=3)
    return application


class TestBrokerApi:
    def test_inventory_requires_staff(self):
        from app.core.db import get_db
        from app.main import create_app

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            application, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/admin/inventory")
        assert resp.status_code == 401, resp.text

    def test_market_intel_200(self):
        from app.schemas.sourcing import MarketIntelRow

        application = _staff_app(MagicMock())
        with patch("app.api.health._check_redis", return_value="ok"), patch(
            "app.api.sourcing.sourcing_service"
        ) as svc, TestClient(application) as tc:
            svc.market_overview.return_value = [
                MarketIntelRow(code="HDPE", buyers=14, sellers=8, avg_seller_price=1085.0, avg_buyer_target=1045.0, spread=40.0)
            ]
            resp = tc.get("/api/v1/admin/intel/market")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["spread"] == 40.0

    def test_source_request_404_when_missing(self):
        mock_db = MagicMock()
        mock_db.get.return_value = None
        application = _staff_app(mock_db)
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as tc:
            resp = tc.post("/api/v1/admin/requests/999/source")
        assert resp.status_code == 404, resp.text
