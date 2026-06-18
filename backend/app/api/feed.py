"""
GET /feed — keyset-paginated live market feed from v_live_feed.
GET /feed/stream — SSE endpoint delivering new entity IDs from Redis pub/sub.

Phase 4, Plan 01: Live Market Feed backend (REQ-live-feed / FR-10).

Security:
  T-04-01: Both endpoints require a valid staff JWT (get_current_staff_user);
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
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user, get_current_staff_user_sse
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
    return datetime.datetime.now(tz=datetime.timezone.utc) - delta


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

    # Normalize volume/price: may be Decimal, float, str, or None
    volume = decimal.Decimal(str(volume_raw)) if volume_raw is not None else None
    price = decimal.Decimal(str(price_raw)) if price_raw is not None else None

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
    db: Session = Depends(get_db),
    _current_user: StaffUser = Depends(get_current_staff_user),
) -> FeedPage:
    """Return a keyset-paginated page of live market feed items.

    Filters:
    - cursor_event_at + cursor_id: keyset cursor for the next page
    - kind: filter by signal/request kind (e.g. 'offer', 'buy_request')
    - product_id: filter by product
    - source: filter by origin ('signal' or 'request')
    - urgency: filter by urgency level
    - period: preset duration lower-bound on event_at ('7d', '30d', '90d', etc.)

    Returns:
        FeedPage with items + next_cursor_event_at / next_cursor_id.
        Both cursors are None when there are no more rows.
    """
    # Resolve period preset to absolute lower-bound timestamp
    period_lower_bound = _resolve_period(period)

    # Keyset SELECT over v_live_feed
    # T-04-02: all params bound — no string interpolation
    # T-04-03: keyset pagination only — no position-based pagination
    query = sa.text(
        """
        SELECT id, origin, kind, product_id, grade_text, volume,
               price, currency, region, urgency, status, event_at
        FROM v_live_feed
        WHERE
            (CAST(:cursor_ea AS timestamptz) IS NULL
             OR event_at < CAST(:cursor_ea AS timestamptz)
             OR (event_at = CAST(:cursor_ea AS timestamptz) AND id < CAST(:cursor_id AS bigint)))
          AND (CAST(:kind AS text) IS NULL OR kind = CAST(:kind AS text))
          AND (CAST(:product_id AS integer) IS NULL OR product_id = CAST(:product_id AS integer))
          AND (CAST(:source AS text) IS NULL OR origin = CAST(:source AS text))
          AND (CAST(:urgency AS text) IS NULL OR urgency::text = CAST(:urgency AS text))
          AND (CAST(:period_lower AS timestamptz) IS NULL OR event_at >= CAST(:period_lower AS timestamptz))
        ORDER BY event_at DESC, id DESC
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
    _current_user: StaffUser = Depends(get_current_staff_user_sse),
) -> StreamingResponse:
    """Stream new entity IDs via Server-Sent Events.

    Each message from the `feed:new` Redis pub/sub channel is emitted as:
        data: {entity_ref}\\n\\n

    The browser-side SSE hook calls queryClient.invalidateQueries(['feed'])
    on each message to trigger a feed refresh.

    Headers:
    - Cache-Control: no-cache — prevents browser/proxy caching
    - X-Accel-Buffering: no — prevents nginx from buffering SSE frames (Pitfall 3)
    """

    async def event_generator() -> Any:
        async for msg in subscribe_feed_events():
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
