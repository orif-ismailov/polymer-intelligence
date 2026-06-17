"""
Dashboard schemas — Pydantic v2 models for the live market feed and requests APIs.

Phase 4, Plan 01: Feed endpoint response models (FeedItem, FeedPage).
Phase 4, Plan 04: Purchase Requests response models (RequestListOut, RequestDetailOut,
                   RequestPatch, StaffUserItem).

FeedItem maps to the v_live_feed columns (normalized signals + requests union).
FeedPage wraps a list of FeedItem with keyset pagination cursors.
RequestListOut / RequestDetailOut are the dashboard staff views (not client-facing).
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

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


# ── Purchase Requests schemas (Phase 4, Plan 04) ──────────────────────────────


class RequestFileOut(BaseModel):
    """File attachment summary for a request (Phase 4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    mime_type: str | None
    size_bytes: int | None
    storage_path: str | None
    created_at: datetime.datetime


class RequestListOut(BaseModel):
    """Single row in the dashboard requests table (list view).

    Staff-only view — NOT the client-facing RequestOut from webapp schemas.
    AI fields (match_score / demand_level / recommendation) are always null in
    Phase 4 (D-01); the field shape is preserved so Phase 5 can fill them in
    without a schema change.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    status: str                             # RequestStatus value as string
    product_id: int
    grade_text: str | None
    polymer_type: str | None
    volume: decimal.Decimal
    volume_unit: str
    target_price: decimal.Decimal | None
    currency: str
    urgency: str                            # Urgency value as string
    assigned_to: int | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RequestDetailOut(BaseModel):
    """Full detail view for a single request on the dashboard.

    Extends RequestListOut with:
    - price_analysis: D-02 real computation from price_points (may be None).
    - ai: D-01 placeholder — echoes the request.ai JSONB column as-is
          (match_score/demand_level/recommendation are null in Phase 4).
    - contact_available: True when clients.telegram_user_id IS NOT NULL (D-11).
    - files: list of RequestFileOut summaries.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    status: str
    product_id: int
    grade_text: str | None
    polymer_type: str | None
    volume: decimal.Decimal
    volume_unit: str
    target_price: decimal.Decimal | None
    currency: str
    incoterms: str
    destination_country: str
    port_or_city: str | None
    desired_date: datetime.date | None
    validity_days: int
    urgency: str
    comment: str | None
    assigned_to: int | None
    # D-01: AI fields — null in Phase 4, shape preserved for Phase 5
    ai: dict[str, Any]
    # D-02: Real price analysis from price_points (computed server-side)
    price_analysis: dict[str, Any] | None
    # D-11: Contact Buyer availability
    contact_available: bool
    files: list[RequestFileOut]
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RequestPatch(BaseModel):
    """Body schema for PATCH /requests/{id}.

    All fields are optional; caller sends only the fields to update.
    - status: routes through request_service.transition_status (D-12 machine).
    - assigned_to: staff user id to assign as owner.
    - note: free-text note to attach to the request audit trail.
    """

    status: str | None = None           # RequestStatus value (validated in router)
    assigned_to: int | None = None
    note: str | None = None


# ── Admin schemas (Phase 4, Plan 04) ─────────────────────────────────────────


class StaffUserItem(BaseModel):
    """Single staff user in GET /admin/users.

    Security (T-04-13): never includes password_hash.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str                           # StaffRole value as string
    is_active: bool
    created_at: datetime.datetime
