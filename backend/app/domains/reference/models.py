"""
Reference tables: products, product_grades, fx_rates.

Also contains Phase-2 dictionary and classification tables:
- product_synonyms (v1.2 addition — migration 0002)
- manual_classification_queue (v1.2 addition — migration 0002)

These are the static reference data that all other tables reference.
Seeded by backend/app/seed/seed_reference.py on first start.

DDL source: docs/polymer-intelligence-db-architecture.md §1 + §v1.2 additions.
"""

from __future__ import annotations

import datetime
import decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
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
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_tr: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class ProductSynonym(Base):
    """Product synonym dictionary for relevance classification.

    Maps free-text synonyms (RU/UZ/EN/abbreviation) to product IDs.
    Admin-top-up-able: new rows can be added at runtime without code changes
    and are picked up immediately by relevance_service.match_product().

    v1.2 addition — created by migration 0002.
    """

    __tablename__ = "product_synonyms"
    __table_args__ = (
        UniqueConstraint("synonym_norm", name="uq_product_synonyms_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("products.id"),
        nullable=False,
    )
    synonym: Mapped[str] = mapped_column(Text, nullable=False)
    synonym_norm: Mapped[str] = mapped_column(Text, nullable=False)
    # 'seed' for synonyms.json entries, 'admin' for runtime admin-added rows
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="seed",
        server_default="seed",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    product: Mapped[Product] = relationship("Product")


class BankRegisterImport(Base):
    """One load of the Central Bank's branch register — seeded or uploaded.

    The newest row is the live register; older ones are kept so an operator can
    see when the list last changed and what it came from. `file_created_at` is
    the register's OWN publication date, which is the only thing that says
    whether a copy is stale — the upload timestamp says when we noticed, not when
    the CB published.

    `uploaded_by` is NULL for the seeded load, which is how "shipped with the
    release" is told apart from "a person replaced it".
    """

    __tablename__ = "bank_register_imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    #: sha256 of the uploaded bytes — makes re-loading the same file a no-op.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_created_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BankBranch(Base):
    """A bank branch, keyed by its MFO — the register's «Код филиала».

    `mfo` is the natural key and is UNIQUE, like every other reference table here
    (`products.code`, `substances.code`). `String(5)` matches
    `company_bank_accounts.bank_mfo`, which is the column this table exists to
    give a name to.

    Branches of all four types are kept (CB units, head offices, payment centres
    and ordinary branches): a company's account sits at a branch, not at a head
    office, and every row names its parent bank either way.
    """

    __tablename__ = "bank_branches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mfo: Mapped[str] = mapped_column(String(5), nullable=False, unique=True, index=True)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    branch_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bank_register_imports.id", ondelete="CASCADE"), nullable=False
    )


class ManualClassificationItem(Base):
    """Queue for raw_items whose product text was not recognized by the relevance service.

    Unrecognized goods route here instead of triggering a source_failure alert
    (REQ-uzex-parser). UNIQUE(raw_item_id) ensures one queue entry per raw item.

    v1.2 addition — created by migration 0002.
    """

    __tablename__ = "manual_classification_queue"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_manual_classification_raw_item"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("raw_items.id"),
        nullable=False,
    )
    # Truncated to 512 chars before insert (T-02-05: DoS via oversized text)
    product_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default="pending",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
