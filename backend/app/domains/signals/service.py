"""
Signal creation service for parsed UZEX rows.

Provides create_signal_from_parse(session, raw_item, parsed) which builds a Signal
ORM object from a parsed UZEX raw_item payload dict.

Design:
- kind is derived from the payload section field:
    offers         → sell_offer
    deals          → deal
    contracts      → price_quote
    buy/requests   → buy_request
    (anything else → sell_offer as safe default)
- volume/price are Decimal-coerced with safe fallback to None on malformed values (T-02-15)
- counterparty_text is copied from the payload (raw name before counterparty linking)
- event_at comes from payload event_date (ISO 8601 with tz), fallback to raw_item.event_at

Security:
  T-02-15: Decimal coercion uses try/except — never eval()/float() for money.
  T-02-16: Signal is built via ORM (no f-string SQL).
"""

from __future__ import annotations

import datetime
import decimal
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domains.signals.models import Signal
from app.models.enums import PriceBasis, SignalKind

if TYPE_CHECKING:
    from app.domains.signals.source_models import RawItem

logger = logging.getLogger(__name__)

# Section → SignalKind mapping
_SECTION_TO_KIND: dict[str, SignalKind] = {
    "offers": SignalKind.sell_offer,
    "offer": SignalKind.sell_offer,
    "sell_offer": SignalKind.sell_offer,
    "deals": SignalKind.deal,
    "deal": SignalKind.deal,
    "contracts": SignalKind.price_quote,
    "contract": SignalKind.price_quote,
    "price_quote": SignalKind.price_quote,
    "quotations": SignalKind.price_quote,
    "quotation": SignalKind.price_quote,
    "buy": SignalKind.buy_request,
    "buy_request": SignalKind.buy_request,
    "requests": SignalKind.buy_request,
}


def _safe_decimal(value: object) -> decimal.Decimal | None:
    """Coerce a value to Decimal, returning None on failure (T-02-15).

    Handles locale-format numbers with comma as decimal separator (e.g.
    ``'8500000,0000'`` from UZEX HTML tables) by replacing the first comma
    that looks like a decimal marker (digits on both sides with ≤4 decimal
    digits) with a dot.  Thousands-separator commas (e.g. ``'8,500,000'``) are
    stripped entirely before conversion.

    Never uses float() or eval() — strict Decimal parsing only.

    Args:
        value: Any value from an untrusted payload (str, int, float, None, etc.)

    Returns:
        Decimal if parseable and finite; None if malformed, None input, or non-finite.
    """
    if value is None:
        return None
    import re as _re  # noqa: PLC0415
    raw = str(value).strip()

    # Normalize locale-format numbers:
    # Case 1: Single comma with ≤4 trailing digits → decimal separator
    #         e.g. '8500000,0000' → '8500000.0000'
    # Case 2: Multiple commas (thousands separators) → strip all commas
    #         e.g. '8,500,000' → '8500000'
    comma_count = raw.count(",")
    if comma_count == 1:
        # Check if trailing digits after comma look like decimal (≤4 digits after comma)
        m = _re.match(r"^(-?\d[\d\s]*),(\d{1,4})$", raw.replace(" ", ""))
        raw = (
            m.group(1).replace(" ", "") + "." + m.group(2)
            if m
            else raw.replace(",", "")
        )
    elif comma_count > 1:
        # Multiple commas → all are thousands separators
        raw = raw.replace(",", "")

    try:
        d = decimal.Decimal(raw)
        # Reject NaN and Inf (T-02-15)
        if not d.is_finite():
            return None
        return d
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None


def _parse_event_at(payload: dict[str, object], raw_item: RawItem) -> datetime.datetime:
    """Extract event_at from payload event_date field or fall back to raw_item.event_at.

    Args:
        payload: The raw_item.payload dict.
        raw_item: The RawItem ORM object.

    Returns:
        A timezone-aware UTC datetime.
    """
    event_date_raw = payload.get("event_date") or payload.get("event_at")
    if event_date_raw:
        try:
            dt = datetime.datetime.fromisoformat(str(event_date_raw))
            # Ensure timezone-aware (convert to UTC if tz is present)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return dt.astimezone(datetime.UTC)
        except (ValueError, TypeError):
            pass

    # Fall back to raw_item.event_at or current UTC time
    if raw_item.event_at is not None:
        return raw_item.event_at

    return datetime.datetime.now(tz=datetime.UTC)


def create_signal_from_parse(
    session: Session,
    raw_item: RawItem,
    parsed: Mapping[str, object],
) -> Signal:
    """Build a Signal ORM object from a parsed UZEX raw_item.

    The Signal is instantiated but NOT added to the session here — the caller
    (parse_raw_item task) is responsible for session.add() and commit.

    Args:
        session: Active SQLAlchemy session (not used for writes here; present for
                 potential future grade lookups or product enrichment).
        raw_item: The RawItem ORM object (for source_id, id, event_at).
        parsed: Dict from relevance + grade resolution:
            - product_id (int | None): resolved product_id
            - grade_id (int | None): resolved grade_id (None if no DB match)
            - grade_text (str | None): raw grade token from extract_grade

    Returns:
        Signal ORM object ready for session.add().

    Security:
        - T-02-15: Decimal coercion for volume/price via _safe_decimal
        - T-02-16: ORM-based construction (no raw SQL)
    """
    payload: dict[str, object] = raw_item.payload or {}

    # Derive SignalKind from section field
    section_raw = str(payload.get("section", "")).lower().strip()
    kind = _SECTION_TO_KIND.get(section_raw, SignalKind.sell_offer)

    # Coerce volume and price (T-02-15: strict Decimal, never float)
    volume = _safe_decimal(payload.get("volume"))
    price = _safe_decimal(payload.get("price"))

    # Currency (3-char cap, None if missing)
    currency_raw = payload.get("currency")
    currency: str | None = str(currency_raw).strip()[:3] if currency_raw else None

    # Counterparty text (raw name before counterparty linking)
    counterparty_text_raw = payload.get("counterparty_text")
    counterparty_text: str | None = (
        str(counterparty_text_raw).strip() if counterparty_text_raw else None
    )

    # Region / delivery-warehouse location (e.g. UZEX "Omborning joylashuvi")
    region_raw = payload.get("region")
    region: str | None = str(region_raw).strip() if region_raw else None

    # Volume unit (default MT)
    volume_unit_raw = payload.get("volume_unit", "MT")
    volume_unit = str(volume_unit_raw).strip() if volume_unit_raw else "MT"

    # Event time
    event_at = _parse_event_at(payload, raw_item)

    signal = Signal(
        kind=kind,
        source_id=raw_item.source_id,
        raw_item_id=raw_item.id,
        product_id=parsed.get("product_id"),
        grade_id=parsed.get("grade_id"),
        grade_text=parsed.get("grade_text"),
        volume=volume,
        volume_unit=volume_unit,
        price=price,
        currency=currency,
        price_basis=PriceBasis.unknown,
        region=region,
        destination=None,
        counterparty_id=None,
        counterparty_text=counterparty_text,
        status="new",
        event_at=event_at,
    )

    logger.debug(
        "signal_service.create_signal",
        extra={
            "kind": kind,
            "product_id": parsed.get("product_id"),
            "raw_item_id": raw_item.id,
        },
    )

    return signal


def create_buy_request_signal_from_xarid(
    session: Session,
    raw_item: RawItem,
    *,
    product_id: int | None,
    grade_id: int | None,
    grade_text: str | None,
) -> Signal:
    """Build a buy_request Signal from a structured xarid procurement payload.

    Unlike create_signal_from_parse (UZEX exchange table rows), xarid rows are
    buy-side tenders: the kind is FORCED to buy_request (never inferred from a
    ``section``, which xarid payloads do not carry), and the buyer / quantity /
    price / location come straight from the structured payload. The product is
    resolved upstream (synonym dictionary or LLM) and passed in — the caller drops
    the row when product_id is None, so this always builds a polymer-relevant lead.

    The buyer's phone/email/tender_url stay in raw_items.payload and are surfaced by
    the live-feed contact join (GET /feed), so no contact fields are copied onto the
    signal row itself. ``session`` is accepted for signature parity with the other
    signal builders; no lookups are performed here.
    """
    payload: dict[str, object] = raw_item.payload or {}

    volume = _safe_decimal(payload.get("quantity"))
    price = _safe_decimal(payload.get("price"))

    # xarid reports a currency NAME ("So'm" / "Сўм" / "Сум"), not an ISO code. Normalize
    # the Uzbek som spellings to "UZS" (matching the UZEX signals); otherwise keep the
    # first 3 chars to fit the String(3) column.
    currency_raw = payload.get("currency")
    currency: str | None = None
    if currency_raw:
        cur = str(currency_raw).strip()
        low = cur.lower()
        if any(alias in low for alias in ("сом", "сўм", "сум", "so'm", "som", "so‘m")):
            currency = "UZS"
        else:
            currency = cur[:3]

    unit_raw = payload.get("unit")
    volume_unit = str(unit_raw).strip() if unit_raw else "MT"

    region_raw = payload.get("delivery_location") or payload.get("country")
    region: str | None = str(region_raw).strip() if region_raw else None

    buyer_raw = payload.get("buyer")
    counterparty_text: str | None = str(buyer_raw).strip() if buyer_raw else None

    product_text_raw = payload.get("product_text")
    grade_text_final = grade_text or (
        str(product_text_raw).strip() if product_text_raw else None
    )

    # event_at from the tender's publication date (fallback: deadline, then raw_item).
    event_payload = dict(payload)
    event_payload.setdefault(
        "event_at", payload.get("publication_date") or payload.get("deadline")
    )
    event_at = _parse_event_at(event_payload, raw_item)

    signal = Signal(
        kind=SignalKind.buy_request,
        source_id=raw_item.source_id,
        raw_item_id=raw_item.id,
        product_id=product_id,
        grade_id=grade_id,
        grade_text=grade_text_final,
        volume=volume,
        volume_unit=volume_unit,
        price=price,
        currency=currency,
        price_basis=PriceBasis.unknown,
        region=region,
        destination=None,
        counterparty_id=None,
        counterparty_text=counterparty_text,
        status="new",
        event_at=event_at,
    )

    logger.debug(
        "signal_service.create_buy_request_from_xarid",
        extra={"product_id": product_id, "raw_item_id": raw_item.id},
    )

    return signal
