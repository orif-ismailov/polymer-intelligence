"""
Dashboard schemas — Pydantic v2 models for the live market feed and requests APIs.

Phase 4, Plan 01: Feed endpoint response models (FeedItem, FeedPage).
Phase 4, Plan 04: Purchase Requests response models (RequestListOut, RequestDetailOut,
                   RequestPatch, StaffUserItem).
Phase 4, Plan 06: Source constructor response models (SourceHealthItem, SourceCreate,
                   SourcePatch, SourceTestOut).
Phase 4, Plan 07: Alert rules + prices response models (AlertRuleCreate, AlertRulePatch,
                   AlertRuleOut, AlertOut, PriceSeriesOut).

FeedItem maps to the v_live_feed columns (normalized signals + requests union).
FeedPage wraps a list of FeedItem with keyset pagination cursors.
RequestListOut / RequestDetailOut are the dashboard staff views (not client-facing).
SourceHealthItem / SourceCreate / SourcePatch / SourceTestOut are the wizard API schemas.
AlertRuleCreate / AlertRulePatch / AlertRuleOut / AlertOut are the alert rules CRUD schemas.
PriceSeriesOut is the price series data point schema.
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
    needs_review: bool               # Phase 5: True when ai->>'needs_review'='true'
    # Seller / counterparty contact — lets staff reach the seller from the live feed.
    # Signals only (None for buy_request rows, which are buyers). Populated from
    # signals.counterparty_text + sources.name + raw_items.payload; richness varies by
    # source (exchange rows give a name only; xarid/Telegram carry phone/email/a link).
    seller: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None


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
    product_id: int | None                  # None for a free-typed product (product_text)
    product_text: str | None = None
    grade_text: str | None
    polymer_type: str | None
    volume: decimal.Decimal
    volume_unit: str
    target_price: decimal.Decimal | None
    currency: str
    urgency: str                            # Urgency value as string
    assigned_to: int | None
    # Dual-origin (R2 W4): "client" (TG Mini App) or "company" (portal). company_*
    # are set only for portal-originated requests so the table can badge + link them.
    origin: str = "client"
    company_id: int | None = None
    company_name: str | None = None
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
    product_id: int | None                  # None for a free-typed product (product_text)
    product_text: str | None = None
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
    # Dual-origin (R2 W4): origin badge + company link on the request detail.
    origin: str = "client"
    company_id: int | None = None
    company_name: str | None = None
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


# ── Source Constructor schemas (Phase 4, Plan 06) ─────────────────────────────


class SourceHealthItem(BaseModel):
    """Single source in GET /sources health list.

    Security (T-04-22): never exposes the config column or any credentials.
    Returns only identity + health fields used by the dashboard Sources screen.
    Extends the admin_sources.SourceHealthItem with last_test_ok_at (wizard enable-gate).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    adapter: str
    kind: str
    is_enabled: bool
    last_fetch_at: datetime.datetime | None
    last_success_at: datetime.datetime | None
    consecutive_failures: int
    last_test_ok_at: datetime.datetime | None


class SourceCreate(BaseModel):
    """Body for POST /sources — create a new source via the wizard.

    adapter must be a no-code type (html_table, rss, telegram_channel, llm_page).
    config is validated against the adapter's config_schema in the router.
    """

    adapter: str
    name: str
    config: dict[str, Any]


class SourceDetail(BaseModel):
    """Full single-source view for the edit form (admin-only, includes config).

    Unlike the health list (T-04-22), this deliberately returns `config` so an admin can
    edit a source's feed URL / content_kind / selectors. Scoped to admin + a single id.
    """

    id: int
    name: str
    adapter: str
    kind: str
    country: str | None = None
    group_name: str | None = None
    url: str | None = None
    is_enabled: bool
    last_test_ok_at: datetime.datetime | None = None
    config: dict[str, Any]


class SourcePatch(BaseModel):
    """Body for PATCH /sources/{id}.

    All fields optional (PATCH semantics — only provided fields change). is_enabled=True
    requires last_test_ok_at IS NOT NULL server-side (D-04 invariant / T-04-20).
    Editing `config` re-validates against the adapter schema and resets the tested/enabled
    state, so a changed feed must pass a fresh Test before it can be re-enabled.
    """

    is_enabled: bool | None = None
    name: str | None = None
    country: str | None = None
    group_name: str | None = None
    config: dict[str, Any] | None = None


class SourceTestOut(BaseModel):
    """Response for POST /sources/{id}/test.

    ok: whether the adapter test passed.
    sample_rows: up to 10 normalized signal-draft rows (D-06).
    error: human-readable error message when ok=False.
    """

    ok: bool
    sample_rows: list[dict[str, Any]]
    error: str | None


# ── Alert Rules + Alerts schemas (Phase 4, Plan 07) ───────────────────────────

# Known predicate keys for the Phase-4 alert interpreter (T-04-24).
# Used for server-side validation of rule condition objects.
KNOWN_PREDICATE_KEYS: frozenset[str] = frozenset({
    "kind",
    "product_id",
    "volume_gte",
    "urgency_in",
    "source_kind",
    "lead_score_gte",  # D-07: authored but never matching until Phase 5 AI
})


class AlertRuleCreate(BaseModel):
    """Body for POST /alert-rules — create a new alert rule.

    condition must only use keys from the known predicate set (T-04-24).
    channels stores per-rule delivery targets: [{"type": "telegram_dm", "chat_id": N}].
    """

    name: str
    kind: str = "custom"
    condition: dict[str, Any]    # validated against KNOWN_PREDICATE_KEYS in router
    channels: list[dict[str, Any]]  # [{"type": "telegram_dm", "chat_id": int}]
    is_enabled: bool = True


class AlertRulePatch(BaseModel):
    """Body for PATCH /alert-rules/{id} — update an alert rule (partial update).

    All fields are optional. condition and channels follow same validation as create.
    """

    name: str | None = None
    condition: dict[str, Any] | None = None
    channels: list[dict[str, Any]] | None = None
    is_enabled: bool | None = None


class AlertRuleOut(BaseModel):
    """Single alert rule in GET /alert-rules response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    name: str
    condition: dict[str, Any]
    channels: list[Any]
    is_enabled: bool
    created_by: int | None
    created_at: datetime.datetime


class AlertOut(BaseModel):
    """Single alert in GET /alerts feed (newest-first)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    rule_id: int | None
    severity: str
    title: str
    body: str
    signal_id: int | None
    request_id: int | None
    dedupe_key: str | None
    created_at: datetime.datetime


# ── Price Series schema (Phase 4, Plan 07) ────────────────────────────────────


class PriceSeriesOut(BaseModel):
    """Single data point in GET /prices/series response.

    observed_on: the date (or start of week for >1yr weekly-aggregate points).
    price_avg: average price for the period.
    currency: the price currency (USD / UZS / CNY).
    """

    observed_on: datetime.date
    price_avg: decimal.Decimal
    currency: str


# ── Dashboard Home summary (overview page: KPIs + top panels) ──────────────────


class DashboardKpis(BaseModel):
    """Five KPI counts for the dashboard home header."""

    total_buyers: int        # clients (webapp buyers)
    total_sellers: int       # counterparties with role='seller'
    active_requests: int     # requests not in a terminal status
    hot_leads: int           # signals classified HOT by AI (Phase 5)
    alert_rules: int         # enabled alert rules


class DashboardRequestItem(BaseModel):
    """A row in the home 'Top Buyer Requests' panel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    product_id: int | None
    product: str | None       # product code (e.g. 'PP'), joined from products
    grade_text: str | None
    volume: decimal.Decimal | None
    target_price: decimal.Decimal | None
    currency: str | None
    urgency: str | None
    status: str
    created_at: datetime.datetime


class DashboardOfferItem(BaseModel):
    """A row in the home 'Top Seller Offers' panel (signals kind='sell_offer')."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    product_id: int | None
    product: str | None
    grade_text: str | None
    volume: decimal.Decimal | None
    price: decimal.Decimal | None
    currency: str | None
    region: str | None
    event_at: datetime.datetime


class DashboardAiSignalItem(BaseModel):
    """A row in the home 'AI Market Signals' panel (signals with AI classification)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    product_id: int | None
    product: str | None
    grade_text: str | None
    classification: str | None    # HOT | MEDIUM | LOW
    lead_score: float | None
    needs_review: bool
    event_at: datetime.datetime


class DashboardSummary(BaseModel):
    """GET /dashboard/summary — everything the overview page needs in one call."""

    kpis: DashboardKpis
    top_requests: list[DashboardRequestItem]
    top_offers: list[DashboardOfferItem]
    ai_signals: list[DashboardAiSignalItem]
