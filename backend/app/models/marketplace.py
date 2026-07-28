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
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import (
    OfferAvailability,
    OfferFileKind,
    OfferRequestStatus,
    OfferSaleMode,
    PriceBasis,
    RegulationLevel,
    SellerOfferStatus,
)

if TYPE_CHECKING:
    from app.models.companies import Company
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
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=True
    )                                                                             # dormant portal-company bridge (R1, A1)
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
        # R2 W6 T6.2: backs the portal/webapp market list
        # (WHERE status='approved' ORDER BY published_at DESC).
        Index("ix_seller_offers_status_published", "status", "published_at"),
        Index("ix_seller_offers_product", "product_id"),
        Index("ix_seller_offers_seller", "seller_id"),
        # Dual-origin (R1, A1): an offer comes from a TG seller OR a portal company.
        CheckConstraint(
            "seller_id IS NOT NULL OR company_id IS NOT NULL", name="ck_offer_origin"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable (R1): a portal offer originates from a company, not a TG seller.
    seller_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=True
    )                                                                             # set for portal-published offers
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=True
    )                                                                             # portal author (A1)
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
    # Nullable: made-to-order («под заказ») offers have no fixed stock qty and no unit
    # price (price is "по запросу"). In-stock offers keep a positive value — enforced in
    # the API schema (SellerOfferCreate), not the DB. See migration 0013.
    qty_available: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    qty_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
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
    # ── How the seller trades this offer (P4 W1) ──────────────────────────────
    # Production/sourcing lead time. Required by the API schema for made-to-order
    # offers, optional here: the column cannot see `availability` to enforce it,
    # and existing rows predate the field.
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_mode: Mapped[OfferSaleMode | None] = mapped_column(
        PgEnum(OfferSaleMode, name="offer_sale_mode", create_type=False), nullable=True
    )
    # "Ready to deal" flags → badges on the market card. Answering an RFQ costs a
    # seller nothing, so it is opt-OUT; signing a contract and holding money in
    # escrow are commitments, so they are opt-in.
    accepts_rfq: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    accepts_contract: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    accepts_escrow: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # ── Chemical compliance (P5) ──────────────────────────────────────────────
    # The registry link is optional: most polymer listings are ordinary goods,
    # and a seller may also type a CAS/HS pair for something we do not carry yet.
    substance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("substances.id", ondelete="SET NULL"), nullable=True
    )
    cas_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    hs_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Regulation is concentration-dependent (acetone is a precursor at ≥60%),
    #: so the seller declares strength and the verdict compares it to the
    #: substance's threshold. NULL is treated as "regulated" — conservative.
    declared_concentration_pct: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    #: Cached verdict (FR-C6) — recomputed on every edit/re-publication, so a
    #: list screen never re-evaluates a page of offers. NULL = never evaluated
    #: (an offer that predates P5).
    compliance_level: Mapped[RegulationLevel | None] = mapped_column(
        PgEnum(RegulationLevel, name="regulation_level", create_type=False), nullable=True
    )
    compliance_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    compliance_missing: Mapped[list[dict[str, str | None]] | None] = mapped_column(
        JSONB, nullable=True
    )
    compliance_checked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    seller: Mapped[Seller | None] = relationship("Seller", back_populates="offers")
    company: Mapped[Company | None] = relationship("Company")  # dual-origin (R1 A1)
    files: Mapped[list[SellerOfferFile]] = relationship(
        "SellerOfferFile",
        back_populates="offer",
        cascade="all, delete-orphan",
        # Upload order is display order, and the first photo is the cover (FR-M2),
        # so the relationship must not come back in arbitrary order.
        order_by="SellerOfferFile.id",
    )

    @property
    def photos(self) -> list[SellerOfferFile]:
        """Attached photos in display order (documents excluded)."""
        return [f for f in self.files if f.kind == OfferFileKind.image]

    @property
    def cover_file_id(self) -> int | None:
        """Id of the cover photo — the first one uploaded (FR-M2), or None."""
        photos = self.photos
        return photos[0].id if photos else None

    # ── Dual-origin display helpers (R1 W5) ───────────────────────────────────
    # A serializer-agnostic view of "who is behind this offer" so every consumer
    # (moderation, public market, TG card) renders seller- and company-origin
    # offers uniformly. company_verified drives the public "verified" badge.

    @property
    def origin(self) -> str:
        return "company" if self.company_id is not None else "seller"

    @property
    def display_name(self) -> str | None:
        if self.company_id is not None and self.company is not None:
            return self.company.short_name or self.company.legal_name
        if self.seller is not None:
            return self.seller.company_name
        return None

    @property
    def company_verified(self) -> bool:
        from app.models.enums import CompanyStatus  # noqa: PLC0415

        return self.company is not None and self.company.status == CompanyStatus.verified

    @property
    def business_roles(self) -> list[str]:
        """CONFIRMED business roles of the company behind this offer (P4 W2).

        Confirmed only, deliberately. A company declares its roles when it
        registers and staff confirm them during verification; showing a declared
        role as a badge would let anyone self-award "manufacturer" — which is
        exactly the claim a buyer is using the badge to check.

        Empty for seller-origin (Telegram) offers: there is no portal company
        behind them, so there is nothing to have confirmed.
        """
        from app.models.enums import BusinessRoleStatus  # noqa: PLC0415

        if self.company is None:
            return []
        return [
            str(role.role)
            for role in self.company.business_roles
            if role.status == BusinessRoleStatus.confirmed
        ]


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


class OfferFavorite(Base):
    """A person's bookmarked offer (P4 W1).

    Keyed to the ACCOUNT, not the company: a shortlist is personal, and someone
    switching company hats in the portal should keep their own list. That is also
    why there is no company_id to scope it by.
    """

    __tablename__ = "offer_favorites"
    __table_args__ = (
        UniqueConstraint("user_account_id", "offer_id", name="uq_offer_favorite"),
        Index("ix_offer_favorites_account", "user_account_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seller_offers.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OfferRequest(Base):
    """A buyer's inquiry against a specific approved seller offer ("Request an offer").

    Admin-gated brokerage: the buyer submits qty/target price/message; the inquiry
    lands in `pending` for staff review. On approval it is forwarded to the seller by
    bot DM (WITHOUT the buyer's contact — the team stays the intermediary). Neither
    side sees the other's contact directly.
    """

    __tablename__ = "offer_requests"
    __table_args__ = (
        # Dual-origin (R2, A2): an inquiry comes from a TG client OR a portal
        # company account. The CHECK keeps the origin invariant at the DB level.
        CheckConstraint(
            "client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL",
            name="ck_inquiry_origin",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seller_offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable (R2): a portal inquiry originates from a company account, not a
    # TG client. Exactly one origin is guaranteed by ck_inquiry_origin.
    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=True
    )                                                                             # set for portal-originated inquiries (A2)
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=True
    )                                                                             # portal author (A2)
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
    client: Mapped[Client | None] = relationship("Client")
    company: Mapped[Company | None] = relationship("Company")  # dual-origin (R2 A2)

    # ── Dual-origin display helper (R2 W1) ────────────────────────────────────
    @property
    def origin(self) -> str:
        """"company" for portal-originated inquiries, else "client" (TG Mini App)."""
        return "company" if self.created_by_user_account_id is not None else "client"


class RfqPushLog(Base):
    """One "we told this supplier about this RFQ" record (P4 W3).

    The unique pair IS the dedup rule (FR-A2): the push task inserts with
    ON CONFLICT DO NOTHING, so re-running it never notifies a supplier twice.

    `score` and `rank` are stored rather than recomputed. Staff read this to
    answer "why did we push this to them?", and the weights will change over
    time — a rank re-derived with today's weights would not explain a push made
    last month.
    """

    __tablename__ = "rfq_push_log"
    __table_args__ = (
        UniqueConstraint("request_id", "company_id", name="uq_rfq_push_target"),
        Index("ix_rfq_push_log_request", "request_id", "rank"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    notified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
