"""
Unit tests for the xarid_tenders adapter (buy-side procurement feed).

All HTTP is mocked at app.ingest.http_client.fetch_url (the adapter routes every
request through the SSRF-guarded client via a local import), so these tests make no
network calls. They cover the three behaviours that matter:

  1. windowed ROW_NUMBER pagination terminates via total_count (no infinite loop),
  2. the Stage-A classifier/keyword filter keeps only polymer/petrochemical lots,
  3. a relevant lot maps to a buy_request-shaped RawItemDraft.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.ingest.xarid.adapters import XaridTendersAdapter

_LIST_URL = "https://xarid-api-auction.uzex.uz/Common/GetMinimizedLotsList"


def _lrow(lot_id: int, rn: int, total: int = 3) -> dict[str, Any]:
    """A minimized LIST row (only id/total_count/rn are load-bearing for the walk)."""
    return {
        "id": lot_id,
        "rn": rn,
        "total_count": total,
        "display_no": f"2611100700{lot_id}",
        "category_name": "sample",
        "start_cost": 1.0,
        "region_name": "Ташкент",
        "end_date": "2026-08-01T10:00:00",
    }


# total_count=3, page_size=2 → windows requested at from=1 and from=3, then the
# frm>total guard stops the walk (from=5 is never even requested).
_LIST_WINDOWS: dict[int, list[dict[str, Any]]] = {
    1: [_lrow(101, 1), _lrow(102, 2)],
    3: [_lrow(103, 3)],
}

_DETAILS: dict[str, dict[str, Any]] = {
    # 101 — relevant via classifier division 20 (plastics in primary forms)
    "101": {
        "id": 101,
        "display_no": "26111007000101",
        "category_name": "Изделия резиновые и пластмассовые",
        "customer_name": "Buyer Alpha LLC",
        "phone": "998901112233",
        "email": None,
        "start_cost": 12000000.0,
        "currency_name": "So'm",
        "country_name": "УЗБЕКИСТАН",
        "region_name": "Ташкент",
        "district_name": "Юнусабад",
        "street": "ул. Амира Темура 1",
        "start_date": "2026-07-01T09:00:00",
        "end_date": "2026-08-01T10:00:00",
        "status_name": "Опубликован",
        "js_details": json.dumps(
            [
                {
                    "product_code": "20.16.10.000-001",
                    "product_name": "Полиэтилен HDPE",
                    "quantity": 50.0,
                    "unit_name": "тонна",
                    "price": 240000.0,
                    "description": "HDPE гранула",
                }
            ]
        ),
    },
    # 102 — relevant via keyword (code division 99 is not in the allow-list)
    "102": {
        "id": 102,
        "display_no": "26111007000102",
        "category_name": "Прочее",
        "customer_name": "Buyer Beta",
        "phone": "998907778899",
        "start_cost": 5000000.0,
        "currency_name": "So'm",
        "country_name": "УЗБЕКИСТАН",
        "region_name": "Самарканд",
        "start_date": "2026-07-02T09:00:00",
        "end_date": "2026-08-02T10:00:00",
        "status_name": "Опубликован",
        "js_details": json.dumps(
            [
                {
                    "product_code": "99.99.99.000",
                    "product_name": "Полипропилен гранула H030",
                    "quantity": 30.0,
                    "unit_name": "тонна",
                    "price": 300000.0,
                }
            ]
        ),
    },
    # 103 — IRRELEVANT: metal division 25, no polymer keyword
    "103": {
        "id": 103,
        "display_no": "26111007000103",
        "category_name": "Изделия металлические готовые",
        "customer_name": "Buyer Gamma",
        "phone": "998900000000",
        "start_cost": 8000000.0,
        "currency_name": "So'm",
        "country_name": "УЗБЕКИСТАН",
        "region_name": "Джизак",
        "district_name": "Фариш",
        "street": "ул. 2",
        "start_date": "2026-07-03T09:00:00",
        "end_date": "2026-08-03T10:00:00",
        "status_name": "Опубликован",
        "js_details": json.dumps(
            [
                {
                    "product_code": "25.12.10.000-005",
                    "product_name": "Дверь из алюминиевого профиля",
                    "quantity": 6.0,
                    "unit_name": "шт",
                    "price": 2000000.0,
                }
            ]
        ),
    },
}


async def _fake_fetch(
    url: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    host_delay: float | None = None,
) -> MagicMock:
    """Route LIST (POST by from-window) and DETAIL (GET by id) to canned JSON."""
    resp = MagicMock()
    if method == "POST":
        frm = int((json_body or {}).get("from", 0))
        resp.json.return_value = _LIST_WINDOWS.get(frm, [])
    else:
        lot_id = url.rsplit("/", 1)[-1]
        resp.json.return_value = _DETAILS.get(lot_id, {})
    return resp


def _source(**cfg: Any) -> MagicMock:
    src = MagicMock()
    src.config = {"page_size": 2, **cfg}
    return src


@pytest.mark.asyncio
async def test_fetch_walks_paginates_and_filters() -> None:
    """Walk stops via total_count; only the 2 polymer lots survive the Stage-A filter."""
    adapter = XaridTendersAdapter()
    with patch("app.ingest.http_client.fetch_url", new=_fake_fetch):
        drafts = await adapter.fetch(_source())

    ids = {d.external_id for d in drafts}
    assert ids == {"101", "102"}, f"expected 101+102 (polymer), got {ids}"
    assert all(d.payload is not None and d.payload["kind_hint"] == "buy_request" for d in drafts)


@pytest.mark.asyncio
async def test_relevant_lot_maps_to_buy_request_shape() -> None:
    """A kept lot carries the buyer-lead fields we care about."""
    adapter = XaridTendersAdapter()
    with patch("app.ingest.http_client.fetch_url", new=_fake_fetch):
        drafts = await adapter.fetch(_source())

    d101 = next(d for d in drafts if d.external_id == "101")
    p = d101.payload
    assert p is not None
    assert p["product_text"] == "Полиэтилен HDPE"
    assert p["buyer"] == "Buyer Alpha LLC"
    assert p["phone"] == "998901112233"
    assert p["currency"] == "So'm"
    assert p["tender_url"] == "https://xarid.uzex.uz/auction/detail/101"
    assert p["delivery_location"] == "Ташкент Юнусабад ул. Амира Темура 1"
    assert isinstance(p["products"], list) and len(p["products"]) == 1


@pytest.mark.asyncio
async def test_all_irrelevant_yields_no_drafts() -> None:
    """If nothing matches the classifier/keywords, nothing is emitted."""
    adapter = XaridTendersAdapter()
    single_metal = {1: [_lrow(103, 1, total=1)]}
    with (
        patch.dict(_LIST_WINDOWS, single_metal, clear=True),
        patch("app.ingest.http_client.fetch_url", new=_fake_fetch),
    ):
        drafts = await adapter.fetch(_source())
    assert drafts == []


@pytest.mark.asyncio
async def test_test_button_ok_and_caps_sample_rows() -> None:
    """adapter.test() reports ok and returns a capped (<=10) preview."""
    adapter = XaridTendersAdapter()
    with patch("app.ingest.http_client.fetch_url", new=_fake_fetch):
        result = await adapter.test({"page_size": 2})

    assert result.ok is True, f"test() not ok: {result.error}"
    assert 0 < len(result.sample_rows) <= 10
    assert all("id" in row for row in result.sample_rows)
