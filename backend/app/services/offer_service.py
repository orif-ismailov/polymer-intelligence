"""
Seller marketplace service (Phase 2).

Open self-serve: a Seller is upserted from the verified Telegram identity on first
listing. Offers are created straight into `pending_moderation`; staff approve/reject
them. Only `approved` offers are public. Per-offer moderation is the gate;
`is_verified` is a separate trust badge.

Service axiom (DEC-dep-owns-commit): functions call db.flush() to obtain ids but
NEVER commit — the router owns the transaction.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import SellerOfferStatus
from app.models.marketplace import Seller, SellerOffer
from app.models.reference import Product
from app.schemas.marketplace import CategoryCount, SellerOfferCreate
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def get_or_create_seller(db: Session, *, telegram_user_id: int, data: SellerOfferCreate) -> Seller:
    """Return the Seller for this Telegram identity, creating/refreshing contact info."""
    seller: Seller | None = (
        db.query(Seller).filter(Seller.telegram_user_id == telegram_user_id).first()
    )
    if seller is None:
        seller = Seller(
            telegram_user_id=telegram_user_id,
            company_name=data.company_name,
            contact_name=data.contact_name,
            phone=data.phone,
            telegram_username=data.telegram_username,
            country=data.country,
        )
        db.add(seller)
        db.flush()
        return seller

    # Refresh contact fields when the seller supplies them (latest wins).
    if data.company_name is not None:
        seller.company_name = data.company_name
    if data.contact_name is not None:
        seller.contact_name = data.contact_name
    if data.phone is not None:
        seller.phone = data.phone
    if data.telegram_username is not None:
        seller.telegram_username = data.telegram_username
    db.flush()
    return seller


def create_offer(db: Session, seller: Seller, data: SellerOfferCreate) -> SellerOffer:
    """Create an offer in `pending_moderation`. Does NOT commit."""
    offer = SellerOffer(
        seller_id=seller.id,
        product_id=data.product_id,
        product_text=data.product_text,
        grade_text=data.grade_text,
        polymer_type=data.polymer_type,
        qty_available=data.qty_available,
        qty_unit=data.qty_unit,
        price=data.price,
        currency=data.currency,
        incoterms=data.incoterms,
        warehouse_city=data.warehouse_city,
        country=data.country,
        min_order_qty=data.min_order_qty,
        description=data.description,
        status=SellerOfferStatus.pending_moderation,
    )
    db.add(offer)
    db.flush()
    logger.info("offer_service.create", extra={"offer_id": offer.id, "seller_id": seller.id})
    return offer


def list_seller_offers(db: Session, seller_id: int) -> list[SellerOffer]:
    """All of one seller's offers, newest first (any status)."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.seller_id == seller_id)
        .order_by(SellerOffer.created_at.desc())
        .all()
    )


def list_catalog(
    db: Session,
    *,
    product_id: int | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SellerOffer]:
    """Public catalog: approved offers, optionally filtered by product / free-text."""
    query = db.query(SellerOffer).filter(SellerOffer.status == SellerOfferStatus.approved)
    if product_id is not None:
        query = query.filter(SellerOffer.product_id == product_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                SellerOffer.product_text.ilike(like),
                SellerOffer.grade_text.ilike(like),
                SellerOffer.polymer_type.ilike(like),
            )
        )
    return (
        query.order_by(SellerOffer.published_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
        .all()
    )


def get_catalog_offer(db: Session, offer_id: int) -> SellerOffer | None:
    """A single approved (public) offer, or None."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.status == SellerOfferStatus.approved)
        .first()
    )


def list_pending(db: Session) -> list[SellerOffer]:
    """Offers awaiting moderation, oldest first (FIFO queue)."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.status == SellerOfferStatus.pending_moderation)
        .order_by(SellerOffer.created_at.asc())
        .all()
    )


def category_counts(db: Session) -> list[CategoryCount]:
    """Per-product count of approved offers (catalog category chips)."""
    rows = (
        db.query(Product.code, func.count(SellerOffer.id))
        .join(SellerOffer, SellerOffer.product_id == Product.id)
        .filter(SellerOffer.status == SellerOfferStatus.approved)
        .group_by(Product.code)
        .order_by(func.count(SellerOffer.id).desc())
        .all()
    )
    return [CategoryCount(code=str(code), count=int(count)) for code, count in rows]


def moderate_offer(
    db: Session,
    offer: SellerOffer,
    staff_user_id: int,
    *,
    approve: bool,
    note: str | None = None,
) -> SellerOffer:
    """Approve or reject a pending offer; write an audit row. Does NOT commit.

    Approved offers become public (published_at set). Rejected offers carry the note
    back to the seller. (Analytics parity — emitting a sell_offer signal on approval —
    is a follow-up; signal_id stays NULL for now.)
    """
    if approve:
        offer.status = SellerOfferStatus.approved
        offer.published_at = utcnow()
    else:
        offer.status = SellerOfferStatus.rejected
    offer.moderated_by = staff_user_id
    offer.moderation_note = note
    db.flush()

    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="offer.approve" if approve else "offer.reject",
        entity="seller_offers",
        entity_id=str(offer.id),
        details={"note": note} if note else {},
    )
    logger.info(
        "offer_service.moderate",
        extra={"offer_id": offer.id, "approve": approve, "staff_user_id": staff_user_id},
    )
    return offer
