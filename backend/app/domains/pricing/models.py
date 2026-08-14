"""
Price points — derived price data layer.

DDL source: docs/polymer-intelligence-db-architecture.md §6.

price_points is a derived layer computed from:
(a) nightly aggregation job from signals with kind='deal'
(b) direct writes from external index cron jobs (SunSirs, DCE)

UI price charts read ONLY from this table (DEC-single-signal-stream).
"""

from __future__ import annotations

import datetime
import decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import PricePointKind


class PricePoint(Base):
    """Derived price series entry (aggregated deal prices or external index)."""

    __tablename__ = "price_points"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "source_id",
            "product_id",
            "grade_id",
            "market",
            "observed_on",
            name="uq_price_points_kind_source_product_grade_market_date",
        ),
        Index(
            "ix_price_points_product_market_observed",
            "product_id",
            "market",
            "observed_on",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[PricePointKind] = mapped_column(
        PgEnum(PricePointKind, name="price_point_kind", create_type=False),
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("products.id"), nullable=False
    )
    grade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("product_grades.id"), nullable=True
    )
    market: Mapped[str] = mapped_column(Text, nullable=False)                    # 'UZ', 'CN', 'DCE'
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    price_avg: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    price_min: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_max: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    volume_total: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    deals_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_on: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
