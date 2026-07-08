"""
Seller marketplace (Phase 2): sellers, seller_offers, seller_offer_files.

Sellers self-register (open self-serve) and publish offers; every offer is
moderated before it appears in the public catalog (status=approved). `is_verified`
is a manually-granted trust badge, NOT a publish gate. On approval an offer also
emits a signals row (kind=sell_offer) so the existing analytics/price machinery
counts user offers — see app/services/offer_service.py.
"""

from __future__ import annotations

import datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import (
    OfferAvailability,
    OfferFileKind,
    OfferRequestStatus,
    PriceBasis,
    SellerOfferStatus,
)

if TYPE_CHECKING:
    from app.models.requests import Client


class Seller(Base):
    """A marketplace seller (self-registered via the Telegram Web App)."""

    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )                                                                             # from initData
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )                                                                             # trust badge, not a publish gate
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    counterparty_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("counterparties.id"), nullable=True
    )                                                                             # link to intelligence loop
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    offers: Mapped[list[SellerOffer]] = relationship(
        "SellerOffer", back_populates="seller"
    )


class SellerOffer(Base):
    """A seller-published catalog offer (moderated before going public)."""

    __tablename__ = "seller_offers"
    __table_args__ = (
        Index("ix_seller_offers_status_created", "status", "created_at"),
        Index("ix_seller_offers_product", "product_id"),
        Index("ix_seller_offers_seller", "seller_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: a seller may list a product not in our catalog (product_text).
    product_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("products.id"), nullable=True
    )
    product_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    polymer_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[OfferAvailability] = mapped_column(
        PgEnum(OfferAvailability, name="offer_availability", create_type=False),
        nullable=False,
        default=OfferAvailability.in_stock,
        server_default="in_stock",
    )
    qty_available: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    qty_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    price: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    incoterms: Mapped[PriceBasis] = mapped_column(
        PgEnum(PriceBasis, name="price_basis", create_type=False),
        nullable=False,
        default=PriceBasis.unknown,
        server_default="unknown",
    )
    warehouse_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    min_order_qty: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SellerOfferStatus] = mapped_column(
        PgEnum(SellerOfferStatus, name="seller_offer_status", create_type=False),
        nullable=False,
        default=SellerOfferStatus.draft,
        server_default="draft",
    )
    moderated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )                                                                             # signals row emitted on approval
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="offers")
    files: Mapped[list[SellerOfferFile]] = relationship(
        "SellerOfferFile", back_populates="offer", cascade="all, delete-orphan"
    )


class SellerOfferFile(Base):
    """A file (image / TDS / certificate) attached to a seller offer."""

    __tablename__ = "seller_offer_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seller_offers.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[OfferFileKind] = mapped_column(
        PgEnum(OfferFileKind, name="offer_file_kind", create_type=False),
        nullable=False,
        default=OfferFileKind.image,
        server_default="image",
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    offer: Mapped[SellerOffer] = relationship("SellerOffer", back_populates="files")


class OfferRequest(Base):
    """A buyer's inquiry against a specific approved seller offer ("Request an offer").

    Admin-gated brokerage: the buyer submits qty/target price/message; the inquiry
    lands in `pending` for staff review. On approval it is forwarded to the seller by
    bot DM (WITHOUT the buyer's contact — the team stays the intermediary). Neither
    side sees the other's contact directly.
    """

    __tablename__ = "offer_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seller_offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    qty_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="MT", server_default="MT")
    target_price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OfferRequestStatus] = mapped_column(
        PgEnum(OfferRequestStatus, name="offer_request_status", native_enum=True),
        nullable=False,
        default=OfferRequestStatus.pending,
        server_default=OfferRequestStatus.pending.value,
        index=True,
    )
    moderated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    forwarded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ── Buyer-edit tracking ───────────────────────────────────────────────────
    # A buyer may revise a submitted inquiry. Editing an already-forwarded
    # (approved) inquiry re-enters moderation (status→pending) and, on re-approval,
    # re-notifies the seller. `last_change_summary` carries the diff since the seller
    # last saw the inquiry so the seller DM can show exactly what changed.
    edited_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )                                                                             # last buyer edit (records that it was modified)
    last_change_summary: Mapped[list[dict[str, str | None]] | None] = mapped_column(
        JSONB, nullable=True
    )                                                                             # [{"field","old","new"}] since the seller last saw it
    seller_notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )                                                                             # True once the seller has been DM'd at least once
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    offer: Mapped[SellerOffer] = relationship("SellerOffer")
    client: Mapped[Client] = relationship("Client")
