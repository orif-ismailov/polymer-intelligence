"""
UZEX data source adapters.

Three adapters covering the main UZEX trade data pages:
  - UzexOffersAdapter    (type_name="uzex_offers")
    Pages: /Trade/OffersSumNew, /Trade/OffersCurrencyNew, /Trade/OffersImportNew
    Fetches open auction positions listed for the day.

  - UzexContractsAdapter (type_name="uzex_contracts")
    Pages: /Trade/ContractsSumNew, /Trade/ContractsCurrencyNew
    Fetches active quotation/contract listings.

  - UzexDealsAdapter     (type_name="uzex_deals")
    Pages: /Trade/List
    Fetches concluded-deal registry.

All adapters:
  - Read selectors and column mappings from source.config (never hardcoded — T-02-14)
  - Route every HTTP request through http_client.fetch_url (SSRF + size cap)
  - Return RawItemDraft objects; no type coercion of values (that is 02-05's job)
  - Cap test() sample_rows at 10 (TestResult contract)
  - Self-register on module import via register_adapter()

Security:
  T-02-11: Row/cell caps enforced in parse_tables.parse_table_rows
  T-02-12: Payload stored via ORM bound parameters; no SQL interpolation
  T-02-13: selectolax lexbor engine; body size capped by http_client
  T-02-14: Selectors in config, not code
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter
from app.ingest.uzex.parse_tables import parse_table_rows

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# Default CSS selector that works across all three UZEX table pages (T-02-14)
_DEFAULT_TABLE_SELECTOR = "table.custom-table-dark"


# ── Config schemas ────────────────────────────────────────────────────────────


class UzexOffersConfig(BaseModel):
    """Config schema for the uzex_offers adapter.

    Fields admin fills in when creating a source of this type (Phase 4 wizard).
    """

    urls: list[str] = Field(
        default_factory=lambda: [
            "https://uzex.uz/Trade/OffersSumNew",
            "https://uzex.uz/Trade/OffersCurrencyNew",
            "https://uzex.uz/Trade/OffersImportNew",
        ]
    )
    table_selector: str = _DEFAULT_TABLE_SELECTOR
    # 0-indexed column-to-field mapping (9 columns):
    # 0=lot, 1=product_text, 2=auction_type(skip), 3=volume, 4=volume_unit,
    # 5=price, 6=(skip count), 7=counterparty_text, 8=event_at
    columns: list[str] = Field(
        default_factory=lambda: [
            "lot",
            "product_text",
            "",  # auction type icon — skip
            "volume",
            "volume_unit",
            "price",
            "",  # today's contract count — skip
            "counterparty_text",
            "event_at",
        ]
    )
    currency: str = "UZS"


class UzexContractsConfig(BaseModel):
    """Config schema for the uzex_contracts adapter."""

    urls: list[str] = Field(
        default_factory=lambda: [
            "https://uzex.uz/Trade/ContractsSumNew",
            "https://uzex.uz/Trade/ContractsCurrencyNew",
        ]
    )
    table_selector: str = _DEFAULT_TABLE_SELECTOR
    # 6 columns: 0=lot, 1=product_text, 2=volume, 3=volume_unit, 4=price, 5=counterparty_text
    columns: list[str] = Field(
        default_factory=lambda: [
            "lot",
            "product_text",
            "volume",
            "volume_unit",
            "price",
            "counterparty_text",
        ]
    )
    currency: str = "UZS"


class UzexDealsConfig(BaseModel):
    """Config schema for the uzex_deals adapter."""

    urls: list[str] = Field(
        default_factory=lambda: [
            "https://uzex.uz/Trade/List",
        ]
    )
    table_selector: str = _DEFAULT_TABLE_SELECTOR
    # 9 columns:
    # 0=event_at, 1=external_id(deal#), 2=price, 3=contract_no, 4=product_text,
    # 5=volume, 6=volume_unit, 7=section, 8=(skip status)
    columns: list[str] = Field(
        default_factory=lambda: [
            "event_at",
            "external_id",
            "price",
            "contract_no",
            "product_text",
            "volume",
            "volume_unit",
            "section",
            "",  # execution status — skip
        ]
    )
    currency: str = "UZS"


# ── Shared helpers ────────────────────────────────────────────────────────────


def _row_external_id(row: dict[str, object], source_url: str, index: int) -> str:
    """Derive a stable external_id for a parsed row.

    Preference order:
    1. ``external_id`` field (deals page — the unique deal number)
    2. ``lot`` field (offers + contracts pages)
    3. Fallback: sha256 of the row text + URL + index (ensures uniqueness even
       when neither field is present)
    """
    ext = str(row.get("external_id") or "").strip()
    if ext:
        return ext

    lot = str(row.get("lot") or "").strip()
    if lot:
        return lot

    # Fallback: hash of the row content so identical rows from different pages
    # still get distinct IDs (index + URL disambiguates)
    row_text = "|".join(f"{k}:{v}" for k, v in sorted(row.items()))
    digest = hashlib.sha256(f"{source_url}#{index}#{row_text}".encode()).hexdigest()[:16]
    return f"row_{digest}"


def _row_content(row: dict[str, object]) -> str:
    """Produce a plain-text content string from a row dict.

    The content string is used for the raw_items.content column (LLM extraction
    in later phases) and as part of the dedup hash.
    """
    parts = []
    for key, value in row.items():
        if value:
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


async def _fetch_and_parse(
    source_urls: list[str],
    config: dict[str, object],
    section_label: str | None = None,
) -> list[RawItemDraft]:
    """Fetch each URL in source_urls, parse the table, return RawItemDraft list."""
    from app.ingest.http_client import fetch_url  # noqa: PLC0415 (avoid Settings init)

    drafts: list[RawItemDraft] = []

    for url in source_urls:
        try:
            response = await fetch_url(url)
        except Exception as exc:
            logger.error(
                "uzex_adapter.fetch_error",
                extra={"url": url, "error": str(exc)},
            )
            continue

        html = response.text
        rows = parse_table_rows(html, config)

        for idx, row in enumerate(rows):
            # Add section label to payload if provided (per-URL metadata)
            payload: dict[str, object] = dict(row)
            if section_label:
                payload["section"] = section_label
            # Inject currency from config
            currency = str(config.get("currency") or "UZS")
            payload["currency"] = currency

            external_id = _row_external_id(row, url, idx)
            content = _row_content(row)

            drafts.append(
                RawItemDraft(
                    external_id=external_id,
                    content=content,
                    payload=payload,
                    event_at=None,  # event_at parsing deferred to 02-05 signals
                )
            )

    logger.info(
        "uzex_adapter.fetch_done",
        extra={"urls": len(source_urls), "drafts": len(drafts)},
    )
    return drafts


# ── Adapters ──────────────────────────────────────────────────────────────────


@dataclass
class UzexOffersAdapter:
    """SourceAdapter for UZEX open auction offers.

    Fetches pages: OffersSumNew, OffersCurrencyNew, OffersImportNew.
    Each page is a server-rendered HTML table (no JS required).
    Selectors and column mapping are read from source.config.
    """

    type_name: str = "uzex_offers"
    config_schema: type[BaseModel] = UzexOffersConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch all configured UZEX offers pages and return row drafts."""
        cfg: dict[str, object] = dict(source.config or {})
        raw_urls = cfg.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexOffersConfig().urls
        return await _fetch_and_parse(urls, cfg)

    async def test(self, config: dict[str, object]) -> TestResult:
        """Fetch the first configured URL and return up to 10 sample rows."""
        raw_urls = config.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexOffersConfig().urls
        if not urls:
            return TestResult(ok=False, error="No URLs configured")

        try:
            drafts = await _fetch_and_parse(urls[:1], config)
            sample: list[dict[str, object]] = [
                {"external_id": d.external_id, **(d.payload or {})}
                for d in drafts[:10]
            ]
            return TestResult(ok=True, sample_rows=sample)
        except Exception as exc:
            logger.error("uzex_offers.test_error", extra={"error": str(exc)})
            return TestResult(ok=False, error=str(exc))


@dataclass
class UzexContractsAdapter:
    """SourceAdapter for UZEX active quotation/contract listings.

    Fetches pages: ContractsSumNew, ContractsCurrencyNew.
    """

    type_name: str = "uzex_contracts"
    config_schema: type[BaseModel] = UzexContractsConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch all configured UZEX contracts pages and return row drafts."""
        cfg: dict[str, object] = dict(source.config or {})
        raw_urls = cfg.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexContractsConfig().urls
        return await _fetch_and_parse(urls, cfg)

    async def test(self, config: dict[str, object]) -> TestResult:
        """Fetch the first configured URL and return up to 10 sample rows."""
        raw_urls = config.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexContractsConfig().urls
        if not urls:
            return TestResult(ok=False, error="No URLs configured")

        try:
            drafts = await _fetch_and_parse(urls[:1], config)
            sample: list[dict[str, object]] = [
                {"external_id": d.external_id, **(d.payload or {})}
                for d in drafts[:10]
            ]
            return TestResult(ok=True, sample_rows=sample)
        except Exception as exc:
            logger.error("uzex_contracts.test_error", extra={"error": str(exc)})
            return TestResult(ok=False, error=str(exc))


@dataclass
class UzexDealsAdapter:
    """SourceAdapter for UZEX concluded-deal registry.

    Fetches page: /Trade/List
    """

    type_name: str = "uzex_deals"
    config_schema: type[BaseModel] = UzexDealsConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch the UZEX deals registry and return row drafts.

        Passes section_label='deals' so that payload['section'] is 'deals'
        (overrides the table column value 'внутренний' which is the market
        section, not the trade type — ensures SignalKind.deal mapping).
        """
        cfg: dict[str, object] = dict(source.config or {})
        raw_urls = cfg.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexDealsConfig().urls
        return await _fetch_and_parse(urls, cfg, section_label="deals")

    async def test(self, config: dict[str, object]) -> TestResult:
        """Fetch the first configured URL and return up to 10 sample rows."""
        raw_urls = config.get("urls")
        urls: list[str] = [str(u) for u in (raw_urls if isinstance(raw_urls, list) else [])] or UzexDealsConfig().urls
        if not urls:
            return TestResult(ok=False, error="No URLs configured")

        try:
            drafts = await _fetch_and_parse(urls[:1], config)
            sample: list[dict[str, object]] = [
                {"external_id": d.external_id, **(d.payload or {})}
                for d in drafts[:10]
            ]
            return TestResult(ok=True, sample_rows=sample)
        except Exception as exc:
            logger.error("uzex_deals.test_error", extra={"error": str(exc)})
            return TestResult(ok=False, error=str(exc))


# ── Self-register on import ────────────────────────────────────────────────────
# All three adapters register when this module is imported.
# The Celery tasks and admin source-types endpoint look up adapters by type_name.
_offers_adapter = UzexOffersAdapter()
_contracts_adapter = UzexContractsAdapter()
_deals_adapter = UzexDealsAdapter()

register_adapter(_offers_adapter)
register_adapter(_contracts_adapter)
register_adapter(_deals_adapter)
