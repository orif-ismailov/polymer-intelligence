"""
Reference tables: products, product_grades, fx_rates.

These are the static reference data that all other tables reference.
Seeded by backend/app/seed/seed_reference.py on first start.

DDL source: docs/polymer-intelligence-db-architecture.md §1.
"""

from __future__ import annotations

import datetime
import decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Product(Base):
    """Polymer product types: PP, HDPE, LDPE, LLDPE, PVC, PET, PS, ABS, etc."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)         # 'PP', 'HDPE'
    name_ru: Mapped[str] = mapped_column(Text, nullable=False)                   # 'Полипропилен'
    name_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(Text, nullable=False, default="polymer")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    grades: Mapped[list[ProductGrade]] = relationship(
        "ProductGrade", back_populates="product"
    )


class ProductGrade(Base):
    """Polymer grades/grades: T30S, H030 SG, F7000, 2420D, etc."""

    __tablename__ = "product_grades"
    __table_args__ = (UniqueConstraint("product_id", "code", name="uq_product_grades_product_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("products.id"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)                      # 'T30S'
    producer: Mapped[str | None] = mapped_column(Text, nullable=True)            # 'Shurtan GCC'
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    product: Mapped[Product] = relationship("Product", back_populates="grades")


class FxRate(Base):
    """Official CBU exchange rates (daily import).

    Stores only official rate to UZS.
    Cross-rates are computed on read, not stored.
    """

    __tablename__ = "fx_rates"

    rate_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    ccy: Mapped[str] = mapped_column(String(3), primary_key=True)                # 'USD', 'CNY', 'RUB'
    rate: Mapped[decimal.Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )                                                                              # UZS per 1 unit of ccy
