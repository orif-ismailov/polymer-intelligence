"""
GET /feed — keyset-paginated live market feed from v_live_feed.
GET /feed/stream — SSE endpoint delivering new entity IDs from Redis pub/sub.

Phase 4, Plan 01: Live Market Feed backend (REQ-live-feed / FR-10).

Security:
  T-04-01: Both endpoints are administrator-only (require_admin / require_admin_sse);
           401 returned when no token or invalid token is presented.
  T-04-02: All filter parameters are bound as SQLAlchemy text params — never
           string-interpolated. Cursor params are typed query params.
  T-04-03: `limit` is capped at le=200; keyset pagination ensures the
           query stays ≤500 ms at 1M signals.

Keyset pagination:
  Cursor = (event_at, id) tuple. To fetch the next page, pass the
  next_cursor_event_at and next_cursor_id from the previous response as
  cursor_event_at and cursor_id in the next request.

  The keyset WHERE clause:
    (:cursor_ea IS NULL OR event_at < :cursor_ea
     OR (event_at = :cursor_ea AND id < :cursor_id))

  This reads: "give me rows strictly before this cursor" and uses the
  composite index on (kind, event_at DESC) that exists on the underlying
  `signals` table.
"""

from __future__ import annotations

import datetime
import decimal
from collections.abc import AsyncIterable
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

from app.api.deps import require_page, require_page_sse
from app.core.db import get_db
from app.core.feed_bus import subscribe_feed_events
from app.models.staff import StaffUser
from app.schemas.dashboard import FeedItem, FeedPage

router = APIRouter(prefix="/feed", tags=["feed"])

# Period preset map: string shorthand → timedelta to subtract from now()
_PERIOD_DELTAS: dict[str, datetime.timedelta] = {
    "1d": datetime.timedelta(days=1),
    "7d": datetime.timedelta(days=7),
    "30d": datetime.timedelta(days=30),
    "90d": datetime.timedelta(days=90),
    "180d": datetime.timedelta(days=180),
    "1y": datetime.timedelta(days=365),
}


def _resolve_period(period: str | None) -> datetime.datetime | None:
    """Resolve a period string to an event_at lower-bound timestamp.

    Returns None if period is None or unrecognized (no lower-bound filter).
    """
    if period is None:
        return None
    delta = _PERIOD_DELTAS.get(period)
    if delta is None:
        return None
    return datetime.datetime.now(tz=datetime.UTC) - delta


def _clean_str(value: Any) -> str | None:
    """Return a trimmed non-empty string, or None for anything else.

    Coerces away NULLs, blanks, and non-str values (e.g. a MagicMock attribute in
    tests) so the optional seller/contact FeedItem fields stay str|None.
    """
    return value.strip() if isinstance(value, str) and value.strip() else None


def _row_attr(row: Any, name: str) -> Any:
    """Attribute access that tolerates rows lacking the column (returns None).

    Real Row objects expose SELECTed columns by name; a plain tuple or a row from
    an older query shape raises AttributeError → None.
    """
    try:
        return getattr(row, name)
    except AttributeError:
        return None


def _row_to_feed_item(row: Any) -> FeedItem:
    """Map a v_live_feed row to a FeedItem schema instance.

    Supports both:
    - Real SQLAlchemy Row objects from sa.text queries (index-based access via _mapping)
    - MagicMock objects from tests (attribute-based access)
    """
    # Try attribute access first (works for both RowMapping._asdict and MagicMocks)
    try:
        id_ = row.id
        origin = row.origin
        kind = row.kind
        product_id = row.product_id
        grade_text = row.grade_text
        volume_raw = row.volume
        price_raw = row.price
        currency = row.currency
        region = row.region
        urgency = row.urgency
        status = row.status
        event_at = row.event_at
        # Phase 5: needs_review from signals.ai JSONB (may be absent on legacy rows)
        try:
            needs_review = bool(row.needs_review)
        except AttributeError:
            needs_review = False
    except AttributeError:
        # Fallback to index-based access for plain tuples
        id_ = row[0]
        origin = row[1]
        kind = row[2]
        product_id = row[3]
        grade_text = row[4]
        volume_raw = row[5]
        price_raw = row[6]
        currency = row[7]
        region = row[8]
        urgency = row[9]
        status = row[10]
        event_at = row[11]
        needs_review = bool(row[12]) if len(row) > 12 else False

    # Normalize volume/price: may be Decimal, float, str, or None
    volume = decimal.Decimal(str(volume_raw)) if volume_raw is not None else None
    price = decimal.Decimal(str(price_raw)) if price_raw is not None else None

    # Seller / contact — present on signal rows (joined from signals + sources +
    # raw_items in the SELECT below); None for request rows and legacy query shapes.
    return FeedItem(
        id=id_,
        origin=origin,
        kind=kind,
        product_id=product_id,
        grade_text=grade_text,
        volume=volume,
        price=price,
        currency=currency,
        region=region,
        urgency=urgency,
        status=status,
        event_at=event_at,
        needs_review=needs_review,
        seller=_clean_str(_row_attr(row, "seller")),
        source_name=_clean_str(_row_attr(row, "source_name")),
        source_url=_clean_str(_row_attr(row, "source_url")),
        contact_phone=_clean_str(_row_attr(row, "contact_phone")),
        contact_email=_clean_str(_row_attr(row, "contact_email")),
    )


@router.get(
    "",
    response_model=FeedPage,
    summary="List live market feed with keyset pagination",
    description=(
        "Returns v_live_feed rows ordered newest-first (event_at DESC, id DESC). "
        "Uses keyset pagination via (cursor_event_at, cursor_id). "
        "All-staff read. "
        "T-04-01: requires valid staff JWT. "
        "T-04-03: limit capped at 200."
    ),
)
def get_feed(
    cursor_event_at: datetime.datetime | None = Query(default=None),
    cursor_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    kind: str | None = Query(default=None),
    product_id: int | None = Query(default=None),
    source: str | None = Query(default=None),
    urgency: str | None = Query(default=None),
    period: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: StaffUser = Depends(require_page(("dashboard", "liveFeed", "offers"), "read")),
) -> FeedPage:
    """Return a keyset-paginated page of live market feed items.

    Filters:
    - cursor_event_at + cursor_id: keyset cursor for the next page
    - kind: filter by signal/request kind (e.g. 'offer', 'buy_request')
    - product_id: filter by product
    - source: filter by origin ('signal' or 'request')
    - urgency: filter by urgency level
    - period: preset duration lower-bound on event_at ('7d', '30d', '90d', etc.)
    - needs_review: filter by AI review flag (Phase 5, bound param — T-05-19)

    Returns:
        FeedPage with items + next_cursor_event_at / next_cursor_id.
        Both cursors are None when there are no more rows.
    """
    # Resolve period preset to absolute lower-bound timestamp
    period_lower_bound = _resolve_period(period)

    # Keyset SELECT over v_live_feed joined to signals for ai JSONB
    # T-04-02: all params bound — no string interpolation
    # T-04-03: keyset pagination only — no position-based pagination
    # T-05-19: needs_review filter uses bound param (no interpolation)
    query = sa.text(
        """
        SELECT v.id, v.origin, v.kind, v.product_id, v.grade_text, v.volume,
               v.price, v.currency, v.region, v.urgency, v.status, v.event_at,
               COALESCE((s.ai->>'needs_review')::boolean, false) AS needs_review,
               s.counterparty_text AS seller,
               src.name AS source_name,
               COALESCE(
                   ri.payload->>'tender_url', ri.payload->>'source_url',
                   ri.payload->>'message_url', ri.payload->>'url', ri.payload->>'link',
                   CASE
                       WHEN ri.payload->>'username' IS NOT NULL AND ri.external_id IS NOT NULL
                       THEN 'https://t.me/' || ltrim(ri.payload->>'username', '@')
                            || '/' || ri.external_id
                       ELSE NULL
                   END,
                   -- Fallback: the source's own listing page (e.g. the UZEX trade board).
                   -- Exchange rows carry no per-lot deep link, so at least link to where
                   -- the offer/deal lives on the exchange. Only http(s) is rendered client-side.
                   src.url
               ) AS source_url,
               COALESCE(ri.payload->>'phone', ri.payload->>'contact_phone') AS contact_phone,
               COALESCE(ri.payload->>'email', ri.payload->>'contact_email') AS contact_email
        FROM v_live_feed v
        LEFT JOIN signals s ON s.id = v.id AND v.origin = 'signal'
        LEFT JOIN sources src ON src.id = s.source_id
        LEFT JOIN raw_items ri ON ri.id = s.raw_item_id
        WHERE
            (CAST(:cursor_ea AS timestamptz) IS NULL
             OR v.event_at < CAST(:cursor_ea AS timestamptz)
             OR (v.event_at = CAST(:cursor_ea AS timestamptz) AND v.id < CAST(:cursor_id AS bigint)))
          AND (CAST(:kind AS text) IS NULL OR v.kind = CAST(:kind AS text))
          AND (CAST(:product_id AS integer) IS NULL OR v.product_id = CAST(:product_id AS integer))
          AND (CAST(:source AS text) IS NULL OR v.origin = CAST(:source AS text))
          AND (CAST(:urgency AS text) IS NULL OR v.urgency::text = CAST(:urgency AS text))
          AND (CAST(:period_lower AS timestamptz) IS NULL OR v.event_at >= CAST(:period_lower AS timestamptz))
          AND (CAST(:needs_review AS boolean) IS NULL
               OR (s.ai->>'needs_review')::boolean = CAST(:needs_review AS boolean))
        ORDER BY v.event_at DESC, v.id DESC
        LIMIT :limit
        """
    )

    params: dict[str, Any] = {
        "cursor_ea": cursor_event_at,
        "cursor_id": cursor_id,
        "kind": kind,
        "product_id": product_id,
        "source": source,
        "urgency": urgency,
        "period_lower": period_lower_bound,
        "needs_review": needs_review,
        "limit": limit,
    }

    rows = db.execute(query, params).fetchall()
    items = [_row_to_feed_item(row) for row in rows]

    # Build next-page cursors from the last (oldest) row in the result
    if items:
        last = items[-1]
        next_cursor_event_at: datetime.datetime | None = last.event_at
        next_cursor_id: int | None = last.id
    else:
        next_cursor_event_at = None
        next_cursor_id = None

    return FeedPage(
        items=items,
        next_cursor_event_at=next_cursor_event_at,
        next_cursor_id=next_cursor_id,
    )


@router.get(
    "/stream",
    response_class=EventSourceResponse,
    summary="SSE stream: new entity IDs from the live feed",
    description=(
        "Server-Sent Events stream delivering new signal/request IDs as they arrive. "
        "Subscribe to trigger a feed refresh via TanStack Query invalidation. "
        "Returns text/event-stream with X-Accel-Buffering: no (prevents nginx buffering). "
        "T-04-01: requires a valid staff JWT — via the Authorization header or, "
        "since EventSource cannot set headers, the access_token query parameter."
    ),
)
async def feed_stream(
    _current_user: StaffUser = Depends(require_page_sse(("dashboard", "liveFeed", "offers"), "read")),
) -> AsyncIterable[ServerSentEvent]:
    """Stream new entity IDs via Server-Sent Events.

    Each message from the `feed:new` Redis pub/sub channel is emitted as
    ``data: {entity_ref}``. The browser hook calls
    ``queryClient.invalidateQueries(['feed'])`` on each one.

    Uses FastAPI's `EventSourceResponse` rather than a hand-rolled
    `StreamingResponse`, for one behavioural reason: it emits a keep-alive comment
    frame (`: ping`) every 15s while the generator is idle. Without that, a feed
    with no traffic hit nginx's `proxy_read_timeout 60s` and was dropped, so every
    open dashboard tab silently reconnected once a minute — each reconnect paying
    for a JWT decode, a StaffUser lookup and a fresh Redis connection. Note this
    reproduces only behind nginx; against a bare dev server the stream just sits
    open, which is why the symptom went unnoticed.

    Framing is now the response class's job, which also removes the manual CR/LF
    sanitisation the old hand-built `f"data: {...}"` needed: `ServerSentEvent`
    rejects a newline in a single-line field outright. The length cap stays — the
    contract is a short entity ref, and a pathological payload should not become a
    multi-megabyte frame.

    `Cache-Control: no-cache` and `X-Accel-Buffering: no` are no longer set here
    because FastAPI's SSE path sets both itself (`fastapi/routing.py`). They are
    still required — without the second one nginx buffers the stream and the feed
    stops being live — so `test_feed_sse` asserts them on the response rather than
    trusting that this stays true across upgrades.
    """
    async for msg in subscribe_feed_events():
        # `raw_data`, NOT `data`: ServerSentEvent JSON-encodes `data` even for
        # plain strings, so `data="signal:42"` would go out as `data: "signal:42"`
        # — quoted. The wire format here predates this change and is a contract
        # with the dashboard hook, so it is kept byte-identical. (Today's consumer
        # ignores the payload and just invalidates the query, but an unannounced
        # format change is not something to leave lying around for the next one.)
        yield ServerSentEvent(
            raw_data=str(msg).replace("\r", "").replace("\n", "")[:128]
        )
