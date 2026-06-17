"""
Dashboard schemas — Pydantic v2 models for the live market feed API.

Phase 4, Plan 01: Feed endpoint response models.

FeedItem maps to the v_live_feed columns (normalized signals + requests union).
FeedPage wraps a list of FeedItem with keyset pagination cursors.
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, ConfigDict


class FeedItem(BaseModel):
    """A single item in the live market feed (from v_live_feed)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str                      # 'signal' or 'request'
    kind: str
    product_id: int | None
    grade_text: str | None
    volume: decimal.Decimal | None
    price: decimal.Decimal | None
    currency: str | None
    region: str | None
    urgency: str | None
    status: str | None
    event_at: datetime.datetime


class FeedPage(BaseModel):
    """Keyset-paginated feed response.

    next_cursor_event_at and next_cursor_id are derived from the last row
    in items and are None when there are no more rows to fetch.
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[FeedItem]
    next_cursor_event_at: datetime.datetime | None
    next_cursor_id: int | None
