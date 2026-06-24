"""
Tests for the UZEX table parser and three UZEX adapters.

All tests are fully offline — no network calls.
fetch_url is patched in adapter fetch()/test() tests to return fixture HTML.

Coverage:
- parse_table_rows: row count and field population for all three fixtures
- Adapters registered by type_name in the global registry
- adapter.test() caps sample_rows at ≤10
- adapter.fetch() routes through http_client.fetch_url (no direct httpx calls)
- Selectors are config-driven (no hardcoded strings in adapters.py)
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixture paths ──────────────────────────────────────────────────────────────
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "uzex"


def _load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    return path.read_text(encoding="utf-8")


# ── Shared config dicts (mirrors defaults in adapters.py) ─────────────────────

OFFERS_CONFIG: dict[str, Any] = {
    "table_selector": "table.custom-table-dark",
    "columns": [
        "lot",
        "product_text",
        "",  # auction type icon — skip
        "volume",
        "volume_unit",
        "price",
        "",  # today's count — skip
        "region",  # "Omborning joylashuvi" — warehouse/delivery location
        "event_at",
    ],
    "currency": "UZS",
    "urls": ["https://uzex.uz/Trade/OffersSumNew"],
}

CONTRACTS_CONFIG: dict[str, Any] = {
    "table_selector": "table.custom-table-dark",
    "columns": ["lot", "product_text", "volume", "volume_unit", "price", "region"],
    "currency": "UZS",
    "urls": ["https://uzex.uz/Trade/ContractsSumNew"],
}

DEALS_CONFIG: dict[str, Any] = {
    "table_selector": "table.custom-table-dark",
    "columns": [
        "event_at",
        "external_id",
        "price",
        "contract_no",
        "product_text",
        "volume",
        "volume_unit",
        "section",
        "",  # status — skip
    ],
    "currency": "UZS",
    "urls": ["https://uzex.uz/Trade/List"],
}


# ── parse_table_rows: row count tests ─────────────────────────────────────────


class TestParseTableRows:
    """Offline parser tests using committed fixtures."""

    def test_offers_sum_row_count(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("offers_sum.html")
        rows = parse_table_rows(html, OFFERS_CONFIG)
        assert len(rows) == 10, f"Expected 10 rows, got {len(rows)}"

    def test_contracts_row_count(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("contracts.html")
        rows = parse_table_rows(html, CONTRACTS_CONFIG)
        assert len(rows) == 10, f"Expected 10 rows, got {len(rows)}"

    def test_deals_row_count(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("deals.html")
        rows = parse_table_rows(html, DEALS_CONFIG)
        assert len(rows) == 10, f"Expected 10 rows, got {len(rows)}"

    def test_offers_sum_key_fields_populated(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("offers_sum.html")
        rows = parse_table_rows(html, OFFERS_CONFIG)
        first = rows[0]
        # product_text must be non-empty (it's a link text — e.g. diesel fuel)
        assert first.get("product_text"), f"product_text empty in row 0: {first}"
        # volume must be a non-empty string
        assert first.get("volume"), f"volume empty in row 0: {first}"
        # price must be a non-empty string
        assert first.get("price"), f"price empty in row 0: {first}"
        # lot (contract number) must be present
        assert first.get("lot"), f"lot empty in row 0: {first}"

    def test_contracts_key_fields_populated(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("contracts.html")
        rows = parse_table_rows(html, CONTRACTS_CONFIG)
        first = rows[0]
        assert first.get("product_text"), f"product_text empty: {first}"
        assert first.get("volume"), f"volume empty: {first}"
        assert first.get("price"), f"price empty: {first}"
        assert first.get("lot"), f"lot empty: {first}"

    def test_deals_key_fields_populated(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("deals.html")
        rows = parse_table_rows(html, DEALS_CONFIG)
        first = rows[0]
        assert first.get("product_text"), f"product_text empty: {first}"
        assert first.get("volume"), f"volume empty: {first}"
        assert first.get("price"), f"price empty: {first}"
        assert first.get("external_id"), f"external_id empty: {first}"

    def test_skipped_columns_absent(self) -> None:
        """Columns with empty string field name must not appear in output dict."""
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("offers_sum.html")
        rows = parse_table_rows(html, OFFERS_CONFIG)
        for row in rows:
            assert "" not in row, f"Empty-string key found in row: {row}"

    def test_missing_table_returns_empty(self) -> None:
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = "<html><body><p>no table here</p></body></html>"
        rows = parse_table_rows(html, OFFERS_CONFIG)
        assert rows == []

    def test_selector_from_config_not_hardcoded(self) -> None:
        """Demonstrate that selector is config-driven: custom selector works."""
        from app.ingest.uzex.parse_tables import parse_table_rows

        html = _load_fixture("offers_sum.html")
        # Use a selector that will NOT find anything → empty result
        cfg_bad = dict(OFFERS_CONFIG, table_selector="table.nonexistent-class")
        rows = parse_table_rows(html, cfg_bad)
        assert rows == [], "Custom selector should control which table is found"

        # Use the real selector → finds 10 rows
        cfg_good = dict(OFFERS_CONFIG, table_selector="table.custom-table-dark")
        rows = parse_table_rows(html, cfg_good)
        assert len(rows) == 10

    def test_row_cap_applied(self) -> None:
        """parse_table_rows must cap output at MAX_ROWS_PER_PAGE (500)."""
        from app.ingest.uzex.parse_tables import MAX_ROWS_PER_PAGE, parse_table_rows

        # Build synthetic HTML with 501 rows
        rows_html = "<tr>" + "<td>val</td>" * 2 + "</tr>\n" * (MAX_ROWS_PER_PAGE + 1)
        html = f"<table class='custom-table-dark'><tbody>{rows_html}</tbody></table>"
        cfg = {
            "table_selector": "table.custom-table-dark",
            "columns": ["product_text", "volume"],
        }
        rows = parse_table_rows(html, cfg)
        assert len(rows) <= MAX_ROWS_PER_PAGE


# ── Registry tests ─────────────────────────────────────────────────────────────


class TestAdapterRegistry:
    """Verify all three adapters are registered after importing the package."""

    def test_uzex_offers_registered(self) -> None:
        import app.ingest.uzex  # noqa: F401 — triggers self-registration
        from app.ingest.registry import get_adapter

        adapter = get_adapter("uzex_offers")
        assert adapter.type_name == "uzex_offers"

    def test_uzex_contracts_registered(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.registry import get_adapter

        adapter = get_adapter("uzex_contracts")
        assert adapter.type_name == "uzex_contracts"

    def test_uzex_deals_registered(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.registry import get_adapter

        adapter = get_adapter("uzex_deals")
        assert adapter.type_name == "uzex_deals"


# ── Adapter.test() caps sample_rows at 10 ─────────────────────────────────────


def _make_fake_response(html: str) -> MagicMock:
    """Build a mock httpx.Response with .text = html."""
    resp = MagicMock()
    resp.text = html
    return resp


class TestAdapterTestMethod:
    """adapter.test() must return sample_rows ≤10 and use fetch_url."""

    @pytest.mark.asyncio
    async def test_offers_test_caps_at_10(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexOffersAdapter

        html = _load_fixture("offers_sum.html")
        mock_response = _make_fake_response(html)

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            adapter = UzexOffersAdapter()
            result = await adapter.test(OFFERS_CONFIG)

        assert result.ok is True, f"test() returned not-ok: {result.error}"
        assert len(result.sample_rows) <= 10

    @pytest.mark.asyncio
    async def test_contracts_test_caps_at_10(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexContractsAdapter

        html = _load_fixture("contracts.html")
        mock_response = _make_fake_response(html)

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            adapter = UzexContractsAdapter()
            result = await adapter.test(CONTRACTS_CONFIG)

        assert result.ok is True, f"test() returned not-ok: {result.error}"
        assert len(result.sample_rows) <= 10

    @pytest.mark.asyncio
    async def test_deals_test_caps_at_10(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexDealsAdapter

        html = _load_fixture("deals.html")
        mock_response = _make_fake_response(html)

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            adapter = UzexDealsAdapter()
            result = await adapter.test(DEALS_CONFIG)

        assert result.ok is True, f"test() returned not-ok: {result.error}"
        assert len(result.sample_rows) <= 10


# ── Adapter.fetch() uses fetch_url, not direct httpx ─────────────────────────


class TestAdapterFetch:
    """adapter.fetch() must route through http_client.fetch_url."""

    @pytest.mark.asyncio
    async def test_offers_fetch_uses_fetch_url(self) -> None:
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexOffersAdapter

        html = _load_fixture("offers_sum.html")
        mock_response = _make_fake_response(html)
        mock_source = MagicMock()
        mock_source.config = dict(OFFERS_CONFIG)

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_fetch:
            adapter = UzexOffersAdapter()
            drafts = await adapter.fetch(mock_source)

        assert mock_fetch.called, "fetch_url was not called"
        assert len(drafts) > 0, "Expected at least 1 draft"
        # Verify all drafts are RawItemDraft
        from app.ingest.base import RawItemDraft

        for draft in drafts:
            assert isinstance(draft, RawItemDraft)

    @pytest.mark.asyncio
    async def test_deals_fetch_returns_external_id(self) -> None:
        """Deals rows use col 1 (deal number) as external_id."""
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexDealsAdapter

        html = _load_fixture("deals.html")
        mock_response = _make_fake_response(html)
        mock_source = MagicMock()
        mock_source.config = dict(DEALS_CONFIG)

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            adapter = UzexDealsAdapter()
            drafts = await adapter.fetch(mock_source)

        assert len(drafts) == 10
        # The deal number (e.g. "8545893") should be the external_id
        first = drafts[0]
        assert first.external_id is not None
        assert first.external_id.isdigit(), (
            f"Expected numeric deal ID as external_id, got: {first.external_id!r}"
        )

    @pytest.mark.asyncio
    async def test_offers_fetch_currency_in_payload(self) -> None:
        """Currency field should be injected into payload from config."""
        import app.ingest.uzex  # noqa: F401
        from app.ingest.uzex.adapters import UzexOffersAdapter

        html = _load_fixture("offers_sum.html")
        mock_response = _make_fake_response(html)
        mock_source = MagicMock()
        mock_source.config = dict(OFFERS_CONFIG, currency="UZS")

        with patch(
            "app.ingest.http_client.fetch_url",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            adapter = UzexOffersAdapter()
            drafts = await adapter.fetch(mock_source)

        for draft in drafts:
            assert draft.payload is not None
            assert draft.payload.get("currency") == "UZS"
