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
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter
from app.ingest.uzex.parse_tables import parse_table_rows

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# Default CSS selector that works across all three UZEX table pages (T-02-14)
_DEFAULT_TABLE_SELECTOR = "table.custom-table-dark"

# ── Pagination defaults (overridable via source.config) ───────────────────────
# UZEX list pages are paginated as ?page=N&length=L. A single page only ever
# returns up to `length` rows, and parse_table_rows caps any page at 500
# (MAX_ROWS_PER_PAGE), so to capture the FULL listing (observed live: ~2000+ open
# offers) the adapter walks pages until a page yields no new rows.
#
# _DEFAULT_PAGE_LENGTH is kept < 500 on purpose: UZEX pins a "featured" lot at the
# top of EVERY page, so a full page returns length+1 rows. Staying under the cap
# guarantees the pin never pushes a real row past the 500-row truncation.
_DEFAULT_PAGE_LENGTH = 400
# Safety bound so a layout change that breaks the stop condition can't loop
# forever (400 * 60 = 24k rows — far above any realistic UZEX listing).
_DEFAULT_MAX_PAGES = 60
# Query-param names UZEX uses for pagination (overridable via config for resilience).
_PAGE_PARAM = "page"
_LENGTH_PARAM = "length"


def _with_query(url: str, **params: object) -> str:
    """Return `url` with the given query params added/overridden (others kept)."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({k: str(v) for k, v in params.items()})
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


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


# Volume-unit tokens → normalized to metric tonnes (MT). UZEX quotes qty in kg or tonnes.
_KG_UNITS: frozenset[str] = frozenset(
    {"кг", "килограмм", "килограммов", "kg", "kilogram", "kilogramm"}
)
_TON_UNITS: frozenset[str] = frozenset(
    {"т", "тн", "тон", "тонна", "тонн", "тонны", "мт", "mt", "ton", "tonne", "tonnes"}
)


def _normalize_price_to_per_mt(payload: dict[str, object]) -> None:
    """In place: turn UZEX's TOTAL contract value + raw qty into a per-MT unit price.

    UZEX ``Mahsulot narxi`` / ``Bazis narxi`` / per-contract price columns hold the TOTAL
    value of the deal (verified live: e.g. urea 361,444,888 for 68 t = 5.3M/t; the same
    urea priced in kg gives the same 5.16M/t). Quantity is in kg or tonnes. Downstream —
    ``signals.price`` and the feed's ``… /MT`` display — expects a per-TONNE unit price,
    so we compute ``total ÷ qty(MT)`` and set volume to MT. Without this, price mixes
    per-tonne, per-kg and whole-contract-total values in one column.

    Raw total is preserved under ``contract_total`` for audit. Rows with a non-mass unit
    (литр, шт…) or an unusable quantity are left untouched (can't derive a per-MT figure).
    """
    unit = str(payload.get("volume_unit") or "").strip().lower()

    def _dec(value: object) -> Decimal | None:
        try:
            s = str(value).strip().replace(" ", "").replace(",", ".")
            return Decimal(s) if s else None
        except (InvalidOperation, ValueError):
            return None

    qty = _dec(payload.get("volume"))
    total = _dec(payload.get("price"))
    if qty is None or qty <= 0:
        return

    if unit in _KG_UNITS:
        vol_mt = qty / Decimal(1000)
    elif unit in _TON_UNITS or unit == "":
        vol_mt = qty
    else:
        return  # unknown/non-mass unit — leave the row as-is

    if vol_mt <= 0:
        return
    if total is not None:
        payload["contract_total"] = str(total)
        payload["price"] = str((total / vol_mt).quantize(Decimal("0.01")))
    payload["volume"] = str(vol_mt)
    payload["volume_unit"] = "MT"


async def _fetch_and_parse(
    source_urls: list[str],
    config: dict[str, object],
    section_label: str | None = None,
) -> list[RawItemDraft]:
    """Fetch each URL in source_urls (paginating), parse, return RawItemDraft list.

    Pagination (config-driven; see the _DEFAULT_PAGE_* constants):
      For each base URL, request ?page=1&length=L, ?page=2&length=L, … until a
      page yields no NEW rows. "New" is judged by external_id so the lot UZEX pins
      at the top of every page is counted once, and an over-run page (which simply
      repeats earlier rows) cleanly terminates the walk. Set config["paginate"] =
      False to fetch a single page (legacy behaviour).

    A fetch error stops pagination for THAT source only (keeping rows already
    collected) and moves on — one bad page never aborts the batch (T-02-17).
    """
    from app.ingest.http_client import fetch_url  # noqa: PLC0415 (avoid Settings init)

    paginate = bool(config.get("paginate", True))
    page_length = int(config.get("page_length") or _DEFAULT_PAGE_LENGTH)
    max_pages = int(config.get("max_pages") or _DEFAULT_MAX_PAGES)
    page_param = str(config.get("page_param") or _PAGE_PARAM)
    length_param = str(config.get("length_param") or _LENGTH_PARAM)
    currency = str(config.get("currency") or "UZS")

    drafts: list[RawItemDraft] = []
    seen_ids: set[str] = set()

    for base_url in source_urls:
        pages_walked = 0
        for page in range(1, (max_pages if paginate else 1) + 1):
            url = (
                _with_query(base_url, **{page_param: page, length_param: page_length})
                if paginate
                else base_url
            )
            try:
                response = await fetch_url(url)
            except Exception as exc:
                logger.error(
                    "uzex_adapter.fetch_error",
                    extra={"url": url, "page": page, "error": str(exc)},
                )
                break  # stop paginating this source; keep what we have (T-02-17)

            rows = parse_table_rows(response.text, config)
            if not rows:
                break  # empty page → past the last page

            new_in_page = 0
            for idx, row in enumerate(rows):
                external_id = _row_external_id(row, url, idx)
                if external_id in seen_ids:
                    continue  # pinned/featured row repeats across pages — dedup
                seen_ids.add(external_id)
                new_in_page += 1

                payload: dict[str, object] = dict(row)
                if section_label:
                    payload["section"] = section_label
                payload["currency"] = currency
                # UZEX prices are the TOTAL contract value + qty in kg/tonnes → convert to
                # a per-MT unit price so signals.price is consistent (feed shows … /MT).
                _normalize_price_to_per_mt(payload)

                drafts.append(
                    RawItemDraft(
                        external_id=external_id,
                        content=_row_content(row),
                        payload=payload,
                        event_at=None,  # event_at parsing deferred to 02-05 signals
                    )
                )

            pages_walked += 1
            # No new rows on this page → we've run past the real data (a repeat or
            # pin-only page). Stop before requesting empty pages forever.
            if new_in_page == 0 or not paginate:
                break

        logger.info(
            "uzex_adapter.url_done",
            extra={"url": base_url, "pages": pages_walked, "running_total": len(drafts)},
        )

    logger.info(
        "uzex_adapter.fetch_done",
        extra={"urls": len(source_urls), "drafts": len(drafts)},
    )
    return drafts


async def _test_sample(
    urls: list[str],
    config: dict[str, object],
    section_label: str | None = None,
) -> TestResult:
    """Diagnostic fetch+parse for the admin "Test source" button.

    Unlike _fetch_and_parse — which logs and *continues* past a failed URL so a
    scheduled ingest job survives one bad page — the Test button must report WHY a
    source yields no data. So:
      - a fetch failure surfaces as ok=False with the exception (instead of being
        swallowed and reported as a silent ok=True / empty sample_rows), and
      - a reachable-but-empty page is reported as ok=False with the HTTP status, body
        size, and selector, so a stale table_selector / bot-block / genuinely-empty
        page can be told apart at a glance.
    """
    from app.ingest.http_client import fetch_url  # noqa: PLC0415 (avoid Settings init)

    if not urls:
        return TestResult(ok=False, error="No URLs configured")

    url = urls[0]
    try:
        response = await fetch_url(url)
    except Exception as exc:
        return TestResult(ok=False, error=f"Fetch failed for {url}: {exc}")

    html = response.text
    rows = parse_table_rows(html, config)
    if not rows:
        selector = str(config.get("table_selector", "table.custom-table-dark"))
        return TestResult(
            ok=False,
            error=(
                f"Fetched {url} (HTTP {response.status_code}, {len(html)} bytes) but "
                f"parsed 0 rows from '{selector}'. The page may be empty or bot-blocked, "
                f"or the table_selector/columns are stale."
            ),
        )

    currency = str(config.get("currency") or "UZS")
    sample: list[dict[str, object]] = []
    for idx, row in enumerate(rows[:10]):
        payload: dict[str, object] = dict(row)
        if section_label:
            payload["section"] = section_label
        payload["currency"] = currency
        sample.append({"external_id": _row_external_id(row, url, idx), **payload})
    return TestResult(ok=True, sample_rows=sample)


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
        return await _test_sample(urls, config)


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
        return await _test_sample(urls, config)


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
        return await _test_sample(urls, config, section_label="deals")


# ── Self-register on import ────────────────────────────────────────────────────
# All three adapters register when this module is imported.
# The Celery tasks and admin source-types endpoint look up adapters by type_name.
_offers_adapter = UzexOffersAdapter()
_contracts_adapter = UzexContractsAdapter()
_deals_adapter = UzexDealsAdapter()

register_adapter(_offers_adapter)
register_adapter(_contracts_adapter)
register_adapter(_deals_adapter)
