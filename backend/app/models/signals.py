"""
Signals — unified market event stream.

DDL source: docs/polymer-intelligence-db-architecture.md §4.

Everything parsed normalizes into signals: UZEX positions, Telegram channel
messages, client requests (via v_live_feed). Dashboard, alerts, and analytics
read from this single table.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import PriceBasis, SignalKind, Urgency


class Signal(Base):
    """A normalized market event (offer, request, deal, quote, news)."""

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_kind_event_at", "kind", "event_at"),
        Index("ix_signals_product_event_at", "product_id", "event_at"),
        Index(
            "ix_signals_counterparty_id_notnull",
            "counterparty_id",
            postgresql_where="counterparty_id IS NOT NULL",
        ),
        Index(
            "ix_signals_status_new",
            "status",
            postgresql_where="status = 'new'",
        ),
        Index(
            "ix_signals_ai_gin",
            "ai",
            postgresql_using="gin",
            postgresql_ops={"ai": "jsonb_path_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[SignalKind] = mapped_column(
        PgEnum(SignalKind, name="signal_kind", create_type=False),
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=False
    )
    raw_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_items.id"), nullable=True
    )

    # Product
    product_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("products.id"), nullable=True
    )
    grade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("product_grades.id"), nullable=True
    )
    grade_text: Mapped[str | None] = mapped_column(Text, nullable=True)          # raw text before grade mapping

    # Parameters
    volume: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    volume_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)       # 'USD', 'UZS', 'CNY'
    price_basis: Mapped[PriceBasis] = mapped_column(
        PgEnum(PriceBasis, name="price_basis", create_type=False),
        nullable=False,
        default=PriceBasis.unknown,
        server_default="unknown",
    )
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Counterparty
    counterparty_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("counterparties.id"), nullable=True
    )
    counterparty_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )                                                                             # raw name before linking

    # AI enrichment (recalculable)
    ai: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    urgency: Mapped[Urgency | None] = mapped_column(
        PgEnum(Urgency, name="urgency", create_type=False),
        nullable=True,
    )                                                                             # denormalized from ai for indexes

    # Lifecycle
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="new", server_default="new"
    )                                                                             # new / viewed / processed / archived
    processed_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )                                                                             # REFERENCES staff_users(id)
    event_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )                                                                             # when it happened at source
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )                                                                             # source-specific extras
