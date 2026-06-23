"""
PostgreSQL ENUM type definitions for the Polymer Intelligence schema.

All 14 ENUM types are declared here and imported by the model modules.
Values are verbatim from the locked DDL (docs/polymer-intelligence-db-architecture.md v1.1).

IMPORTANT: ENUM values must not be changed without a schema migration.
Schema changes only via Alembic migration + DB-doc edit in the same PR (dev-spec §8).
"""

from __future__ import annotations

import enum


class SourceKind(enum.StrEnum):
    """Type of data source."""

    exchange = "exchange"
    telegram_channel = "telegram_channel"
    website = "website"
    webapp = "webapp"
    manual = "manual"
    external_index = "external_index"
    rss = "rss"


class ParseStatus(enum.StrEnum):
    """Processing status of a raw item."""

    pending = "pending"
    parsed = "parsed"
    failed = "failed"
    skipped = "skipped"
    irrelevant = "irrelevant"
    budget_deferred = "budget_deferred"  # Phase 5 G4: rule-based fallback ran, awaiting nightly LLM catch-up


class CounterpartyRole(enum.StrEnum):
    """Market role of a counterparty."""

    buyer = "buyer"
    seller = "seller"
    trader = "trader"
    producer = "producer"
    unknown = "unknown"


class SignalKind(enum.StrEnum):
    """Type of market signal."""

    buy_request = "buy_request"
    sell_offer = "sell_offer"
    deal = "deal"
    price_quote = "price_quote"
    news = "news"


class PriceBasis(enum.StrEnum):
    """Incoterms / delivery basis for price."""

    EXW = "EXW"
    FCA = "FCA"
    FOB = "FOB"
    CIF = "CIF"
    CPT = "CPT"
    DAP = "DAP"
    DDP = "DDP"
    unknown = "unknown"


class Urgency(enum.StrEnum):
    """Urgency / priority level."""

    low = "low"
    medium = "medium"
    high = "high"


class RequestStatus(enum.StrEnum):
    """Client request lifecycle status."""

    new = "new"
    viewed = "viewed"
    in_progress = "in_progress"
    offer_sent = "offer_sent"
    matched = "matched"
    closed = "closed"
    cancelled = "cancelled"


class PricePointKind(enum.StrEnum):
    """Type of derived price point."""

    deal_avg = "deal_avg"
    offer_avg = "offer_avg"
    index = "index"  # type: ignore[assignment]  # "index" shadows str.index() method; DB ENUM value must stay "index"
    futures = "futures"


class AlertKind(enum.StrEnum):
    """Type of alert rule / alert event."""

    new_hot_request = "new_hot_request"
    large_volume = "large_volume"
    price_spike = "price_spike"
    below_market_offer = "below_market_offer"
    new_buyer = "new_buyer"
    source_failure = "source_failure"
    custom = "custom"


class DeliveryChannel(enum.StrEnum):
    """Delivery channel for notifications."""

    telegram_dm = "telegram_dm"
    telegram_channel = "telegram_channel"
    webapp = "webapp"
    dashboard = "dashboard"


class DeliveryStatus(enum.StrEnum):
    """Delivery status for a notification."""

    queued = "queued"
    sent = "sent"
    failed = "failed"


class ReportKind(enum.StrEnum):
    """Type of market report."""

    morning = "morning"
    intraday = "intraday"
    weekly = "weekly"
    custom = "custom"


class ReportStatus(enum.StrEnum):
    """Publication status of a report (human-in-the-loop)."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    published = "published"
    rejected = "rejected"


class StaffRole(enum.StrEnum):
    """Internal staff access role (REQ-roles, enforced in plan 01-03)."""

    admin = "admin"
    analyst = "analyst"
    trader = "trader"
    viewer = "viewer"
