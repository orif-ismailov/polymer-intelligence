"""
Internal sourcing layer (Phase 4): inventory_items, partner_suppliers, sourcing_runs.

These power the AI broker dashboard: our own stock and partner-supplier pricing feed
the per-request sourcing waterfall (inventory → partners → marketplace → import), and
each run is journaled to sourcing_runs (+ stamped into requests.ai). Staff-only data.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

from sqlalchemy import (
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
from app.models.enums import PriceBasis


class InventoryItem(Base):
    """Our own stock — sourcing priority #1."""

    __tablename__ = "inventory_items"
    __table_args__ = (Index("ix_inventory_items_product", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("products.id"), nullable=False
    )
    grade_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty_on_hand: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    qty_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    cost_price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    warehouse_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PartnerSupplier(Base):
    """A known partner supplier with indicative pricing — sourcing priority #2."""

    __tablename__ = "partner_suppliers"
    __table_args__ = (Index("ix_partner_suppliers_product", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    counterparty_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("counterparties.id"), nullable=True
    )
    product_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("products.id"), nullable=True
    )
    grade_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    indicative_price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    incoterms: Mapped[PriceBasis] = mapped_column(
        PgEnum(PriceBasis, name="price_basis", create_type=False),
        nullable=False,
        default=PriceBasis.unknown,
        server_default="unknown",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourcingRun(Base):
    """Audit of one AI sourcing waterfall executed for a buyer request."""

    __tablename__ = "sourcing_runs"
    __table_args__ = (Index("ix_sourcing_runs_request", "request_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )                                                                             # ranked options + market context
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
