"""
xarid.uzex.uz procurement-tender adapter (buy-side demand).

xarid.uzex.uz is Uzbekistan's mandatory public e-procurement portal: BUYERS (state
bodies + enterprises) publish lots they want to PURCHASE and suppliers compete to
sell to them. That makes it the buyer-detection feed — each lot is a concrete
purchase demand we can offer our products against (``kind_hint = buy_request``),
the mirror image of the sell-side ``uzex_*`` exchange adapters.

Unlike the ``uzex_*`` HTML adapters, the portal is an Angular SPA over a JSON
microservices API, so this adapter talks to that API directly (no browser/Playwright
needed — the list/detail endpoints are public, no auth or validation token):

  LIST   POST {list_url}                    body {**list_body, "from": N, "to": M}
         → array of minimized rows; every row carries id, total_count, rn.
  DETAIL GET  {detail_url_template}/{id}
         → full record (customer_name, phone, email, prices, dates, location) +
           js_details[] product line items (product_code, product_name, qty, price…).

Pagination: ``from``/``to`` are 1-indexed SQL ROW_NUMBER window bounds (NOT page
numbers); ``total_count`` on each row is the grand total. We walk fixed windows of
``page_size`` (the auction stored proc raises ORA-01403 on large windows, so keep it
at 20 — the value the portal itself uses) until we pass ``total_count`` or a window
yields no NEW ids — the same "walk until no new rows + MAX_PAGES bound" contract as
the uzex adapters. All requests go through the SSRF-guarded ``http_client``.

Stage-A relevance filter (cheap, deterministic, no LLM): a lot is kept only if any
line item's national-classifier ``product_code`` division is in
``classifier_divisions`` (19 = coke & refined petroleum, 20 = chemicals incl. 20.16
plastics-in-primary-forms, 22 = rubber & plastic) OR a ``keyword`` matches the
product name / description. Everything else is dropped before it reaches the parse
or LLM stage (respecting the daily token budget).

Security:
  - All fetches via http_client.fetch_url (SSRF guard + 25 MB cap + retry+backoff).
  - No credentials: the LIST/DETAIL endpoints are anonymous (public transparency portal).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# Page size kept at the value the portal itself uses (20). The auction stored proc
# raises ORA-01403 ("no data found") on larger windows — do NOT widen this.
_DEFAULT_PAGE_SIZE = 20
# Safety bound so a broken stop-condition can't loop forever (200 * 20 = 4000 rows,
# far above the observed few-hundred live lots per feed).
_DEFAULT_MAX_PAGES = 200

# National goods-classifier divisions (leading 2 digits of product_code) in our
# domain. 19 = coke & refined petroleum, 20 = chemicals (incl. 20.16 plastics in
# primary forms — raw PP/HDPE/PVC), 22 = rubber & plastic products.
_DEFAULT_DIVISIONS = ["19", "20", "22"]

# RU/UZ/EN keyword belt for polymer/petrochemical products — a backstop to the
# classifier when a lot is mis-coded or coded coarsely.
_DEFAULT_KEYWORDS = [
    "полипроп", "полиэтил", "полистирол", "поливинил", "пвх", "pvc", "pet", "пэт",
    "полимер", "пластмасс", "пластик", "полиэфир", "смол", "каучук", "гранул",
    "полиамид", "поликарбонат", "метанол", "бензол", "стирол", "пропилен", "этилен",
    "polipro", "polietil", "plastik", "polimer", "kauchuk", "hdpe", "ldpe", "lldpe",
    "abs", "pom", "pmma",
]


class XaridTendersConfig(BaseModel):
    """Config schema for the xarid_tenders adapter (admin add-source wizard)."""

    model_config = ConfigDict(extra="ignore")

    list_url: str = "https://xarid-api-auction.uzex.uz/Common/GetMinimizedLotsList"
    detail_url_template: str = "https://xarid-api-auction.uzex.uz/Common/GetLot/{id}"
    # Extra fields merged into every LIST request body (auction needs region_ids;
    # the purchase feeds — GetTenders — omit it, so leave it configurable).
    list_body: dict[str, Any] = Field(default_factory=lambda: {"region_ids": []})
    page_size: int = _DEFAULT_PAGE_SIZE
    max_pages: int = _DEFAULT_MAX_PAGES
    classifier_divisions: list[str] = Field(default_factory=lambda: list(_DEFAULT_DIVISIONS))
    keywords: list[str] = Field(default_factory=lambda: list(_DEFAULT_KEYWORDS))
    # Cap detail fetches per run (each id = one GET). None = walk everything.
    max_details: int | None = 500


# ── HTTP helpers ──────────────────────────────────────────────────────────────


async def _list_page(list_url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    """POST one LIST window; return its row array ([] on error envelope / empty)."""
    from app.ingest.http_client import fetch_url  # noqa: PLC0415 (avoid Settings init at import)

    response = await fetch_url(list_url, method="POST", json_body=body)
    data = response.json()
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    # Error envelope like {"status":500,"message":"..."} → treat as no data.
    return []


async def _detail(detail_url_template: str, lot_id: Any) -> dict[str, Any] | None:
    """GET one lot's full detail record; None on error/shape mismatch."""
    from app.ingest.http_client import fetch_url  # noqa: PLC0415

    url = detail_url_template.format(id=lot_id)
    response = await fetch_url(url, method="GET")
    data = response.json()
    return data if isinstance(data, dict) else None


# ── Parsing / mapping ─────────────────────────────────────────────────────────


def _line_items(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the ``js_details`` JSON-string into a list of product line items."""
    raw = detail.get("js_details")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return []
        raw = parsed
    if isinstance(raw, list):
        return [i for i in raw if isinstance(i, dict)]
    return []


def _is_relevant(detail: dict[str, Any], divisions: list[str], keywords: list[str]) -> bool:
    """Stage-A filter: keep only polymer/petrochemical lots (classifier OR keyword)."""
    items = _line_items(detail)
    hay_parts: list[str] = [
        str(detail.get("category_name") or ""),
        str(detail.get("description") or ""),
    ]
    for it in items:
        code = str(it.get("product_code") or "")
        division = code.split(".", 1)[0].strip()
        if division in divisions:
            return True
        hay_parts.append(str(it.get("product_name") or ""))
        hay_parts.append(str(it.get("description") or ""))
    hay = " ".join(hay_parts).lower()
    return any(kw in hay for kw in keywords)


def _to_draft(detail: dict[str, Any], lot_id: Any) -> RawItemDraft:
    """Map a xarid detail record → structured RawItemDraft (kind_hint=buy_request)."""
    items = _line_items(detail)
    first = items[0] if items else {}
    location = " ".join(
        p
        for p in (
            str(detail.get("region_name") or ""),
            str(detail.get("district_name") or ""),
            str(detail.get("street") or ""),
        )
        if p
    ).strip()
    products = [
        {
            "product_code": it.get("product_code"),
            "product_name": it.get("product_name"),
            "quantity": it.get("quantity"),
            "unit_name": it.get("unit_name"),
            "price": it.get("price"),
        }
        for it in items
    ]
    payload: dict[str, object] = {
        "kind_hint": "buy_request",
        "exchange": "UZEX xarid",
        "tender_id": detail.get("display_no"),
        "lot_id": lot_id,
        "country": detail.get("country_name"),
        "buyer": detail.get("customer_name"),
        "category": detail.get("category_name"),
        "product_text": first.get("product_name"),
        "product_code": first.get("product_code"),
        "quantity": first.get("quantity"),
        "unit": first.get("unit_name"),
        "price": detail.get("start_cost"),
        "currency": detail.get("currency_name"),
        "delivery_location": location or None,
        "deadline": detail.get("end_date"),
        "status": detail.get("status_name"),
        "phone": detail.get("phone"),
        "email": detail.get("email"),
        "publication_date": detail.get("start_date") or detail.get("date_ini"),
        "tender_url": f"https://xarid.uzex.uz/auction/detail/{lot_id}",
        "products": products,
    }
    names = ", ".join(str(p["product_name"]) for p in products if p.get("product_name")) or "—"
    content = (
        f"Buyer: {payload['buyer']} | Products: {names} | "
        f"Qty: {payload['quantity']} {payload['unit'] or ''} | "
        f"Budget: {payload['price']} {payload['currency'] or ''} | "
        f"Location: {location} | Deadline: {payload['deadline']}"
    )
    return RawItemDraft(
        external_id=str(lot_id),
        content=content,
        payload=payload,
        # Date strings are kept in the payload; a tz-safe event_at is derived at the
        # parse step (mirrors the uzex adapters, which defer event_at to signals).
        event_at=None,
    )


# ── Fetch orchestration ───────────────────────────────────────────────────────


async def _walk_ids(cfg: XaridTendersConfig) -> list[Any]:
    """Windowed ROW_NUMBER walk of the LIST endpoint → ordered, unique lot ids."""
    ids: list[Any] = []
    seen: set[Any] = set()
    total: int | None = None
    frm = 1
    for _ in range(cfg.max_pages):
        to = frm + cfg.page_size - 1
        body = {**dict(cfg.list_body), "from": frm, "to": to}
        try:
            rows = await _list_page(cfg.list_url, body)
        except Exception as exc:  # noqa: BLE001 — one bad window stops the walk, keeps prior ids
            logger.error("xarid_adapter.list_error", extra={"from": frm, "error": str(exc)})
            break
        if not rows:
            break
        if total is None:
            try:
                total = int(rows[0].get("total_count") or 0)
            except (TypeError, ValueError):
                total = 0
        new_in_page = 0
        for row in rows:
            rid = row.get("id")
            if rid is None or rid in seen:
                continue
            seen.add(rid)
            ids.append(rid)
            new_in_page += 1
        frm += cfg.page_size
        if new_in_page == 0:
            break  # window returned only already-seen rows → past the real data
        if total and frm > total:
            break
    return ids


async def _fetch(cfg: XaridTendersConfig) -> list[RawItemDraft]:
    """Full list → detail → Stage-A filter → RawItemDraft run."""
    ids = await _walk_ids(cfg)
    if cfg.max_details is not None:
        ids = ids[: cfg.max_details]

    drafts: list[RawItemDraft] = []
    for lot_id in ids:
        try:
            detail = await _detail(cfg.detail_url_template, lot_id)
        except Exception as exc:  # noqa: BLE001 — one bad detail never aborts the batch
            logger.warning("xarid_adapter.detail_error", extra={"id": lot_id, "error": str(exc)})
            continue
        if detail is None:
            continue
        if not _is_relevant(detail, cfg.classifier_divisions, cfg.keywords):
            continue
        drafts.append(_to_draft(detail, lot_id))

    logger.info("xarid_adapter.fetch_done", extra={"ids": len(ids), "relevant": len(drafts)})
    return drafts


def _cfg_from(config: dict[str, object]) -> XaridTendersConfig:
    """Build a validated config from source.config, tolerating partial/empty input."""
    try:
        return XaridTendersConfig(**{k: v for k, v in config.items() if v is not None})
    except Exception:  # noqa: BLE001 — fall back to safe defaults on a malformed config
        return XaridTendersConfig()


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class XaridTendersAdapter:
    """SourceAdapter for xarid.uzex.uz procurement tenders (buy-side demand)."""

    type_name: str = "xarid_tenders"
    config_schema: type[BaseModel] = XaridTendersConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch relevant procurement tenders and return structured row drafts."""
        cfg = _cfg_from(dict(source.config or {}))
        return await _fetch(cfg)

    async def test(self, config: dict[str, object]) -> TestResult:
        """Fetch the first LIST window and return up to 10 sample rows for the UI."""
        cfg = _cfg_from(dict(config or {}))
        body = {**dict(cfg.list_body), "from": 1, "to": cfg.page_size}
        try:
            rows = await _list_page(cfg.list_url, body)
        except Exception as exc:  # noqa: BLE001 — the Test button must surface WHY it failed
            return TestResult(ok=False, error=f"List fetch failed for {cfg.list_url}: {exc}")
        if not rows:
            return TestResult(
                ok=False,
                error=(
                    f"Reached {cfg.list_url} but parsed 0 rows — the endpoint may be "
                    "empty right now or the JSON API shape changed."
                ),
            )
        sample: list[dict[str, object]] = [
            {
                "id": r.get("id"),
                "display_no": r.get("display_no"),
                "category_name": r.get("category_name"),
                "start_cost": r.get("start_cost"),
                "region_name": r.get("region_name"),
                "end_date": r.get("end_date"),
                "total_count": r.get("total_count"),
            }
            for r in rows[:10]
        ]
        return TestResult(ok=True, sample_rows=sample)


register_adapter(XaridTendersAdapter())
