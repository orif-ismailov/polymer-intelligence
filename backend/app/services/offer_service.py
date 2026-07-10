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
from app.schemas.marketplace import CategoryCount, SellerOfferCreate, SellerOfferUpdate
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
        availability=data.availability,
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


def update_offer(
    db: Session, offer: SellerOffer, data: SellerOfferUpdate
) -> tuple[SellerOffer, bool]:
    """Apply a seller's revision to their own offer (full-replacement). Does NOT commit.

    Every editable field is replaced from ``data``. Editing an offer that is currently
    public (approved) — or one that was rejected — sends it back to ``pending_moderation``
    so the team re-approves before the change appears in the catalog again (the platform
    invariant: nothing is public without moderation). Draft/pending offers are updated in
    place and keep their status.

    Returns (offer, requeued) where ``requeued`` is True when the edit moved the offer
    back into the moderation queue — the router then re-posts it to the team group.
    """
    offer.product_id = data.product_id
    offer.product_text = data.product_text
    offer.grade_text = data.grade_text
    offer.polymer_type = data.polymer_type
    offer.availability = data.availability
    offer.qty_available = data.qty_available
    offer.qty_unit = data.qty_unit
    offer.price = data.price
    offer.currency = data.currency
    offer.incoterms = data.incoterms
    offer.warehouse_city = data.warehouse_city
    offer.country = data.country
    offer.min_order_qty = data.min_order_qty
    offer.description = data.description

    # An edit to a public (approved) or previously-rejected offer re-enters moderation.
    requeued = offer.status in (SellerOfferStatus.approved, SellerOfferStatus.rejected)
    if requeued:
        offer.status = SellerOfferStatus.pending_moderation
        offer.published_at = None
        offer.moderated_by = None
        offer.moderation_note = None

    db.flush()
    write_audit(
        db=db,
        staff_user_id=None,
        action="offer.edit",
        entity="seller_offers",
        entity_id=str(offer.id),
        details={"via": "seller", "requeued": requeued},
    )
    logger.info(
        "offer_service.update",
        extra={"offer_id": offer.id, "seller_id": offer.seller_id, "requeued": requeued},
    )
    return offer, requeued


def list_seller_offers(db: Session, seller_id: int) -> list[SellerOffer]:
    """All of one seller's offers, newest first (any status)."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.seller_id == seller_id)
        .order_by(SellerOffer.created_at.desc())
        .all()
    )


def seller_id_for(db: Session, telegram_user_id: int | None) -> int | None:
    """Return the Seller id owned by this Telegram identity, or None (cheap id lookup).

    Used to exclude a seller's own offers from the catalog they browse and to flag the
    single-offer detail as owned (``is_own``). Returns None when the caller has never
    listed anything (no Seller row yet) or has no Telegram id.
    """
    if telegram_user_id is None:
        return None
    result: int | None = (
        db.query(Seller.id).filter(Seller.telegram_user_id == telegram_user_id).scalar()
    )
    return result


def get_own_offer(db: Session, offer_id: int, seller_id: int) -> SellerOffer | None:
    """Load an offer only if it belongs to this seller (owner-scoped), else None."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.seller_id == seller_id)
        .first()
    )


def list_catalog(
    db: Session,
    *,
    product_id: int | None = None,
    q: str | None = None,
    exclude_seller_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SellerOffer]:
    """Public catalog: approved offers, optionally filtered by product / free-text.

    When ``exclude_seller_id`` is set, that seller's own listings are omitted — a seller
    browsing the marketplace sees only other sellers' offers (they manage their own under
    "My offers" and cannot inquire on them).
    """
    query = db.query(SellerOffer).filter(SellerOffer.status == SellerOfferStatus.approved)
    if exclude_seller_id is not None:
        query = query.filter(SellerOffer.seller_id != exclude_seller_id)
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


def category_counts(db: Session, *, exclude_seller_id: int | None = None) -> list[CategoryCount]:
    """Per-product count of approved offers (catalog category chips).

    Honours the same own-offer exclusion as :func:`list_catalog` so the chip counts
    match the offers the caller actually sees.
    """
    query = (
        db.query(Product.code, func.count(SellerOffer.id))
        .join(SellerOffer, SellerOffer.product_id == Product.id)
        .filter(SellerOffer.status == SellerOfferStatus.approved)
    )
    if exclude_seller_id is not None:
        query = query.filter(SellerOffer.seller_id != exclude_seller_id)
    rows = (
        query.group_by(Product.code)
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


def moderate_offer_via_telegram(
    db: Session,
    offer: SellerOffer,
    telegram_user_id: int,
    *,
    approve: bool,
    note: str | None = None,
) -> SellerOffer:
    """Approve/reject an offer from the team Telegram group. Does NOT commit.

    Same effect as :func:`moderate_offer` but the actor is a Telegram user (a group
    admin), not a StaffUser — so ``moderated_by`` stays NULL and the acting Telegram
    id is recorded in the audit ``details`` instead. Authorization (must be a group
    admin) is enforced by the caller in the bot handler, not here.
    """
    if approve:
        offer.status = SellerOfferStatus.approved
        offer.published_at = utcnow()
    else:
        offer.status = SellerOfferStatus.rejected
    offer.moderation_note = note
    db.flush()

    details: dict[str, object] = {"via": "telegram", "telegram_user_id": telegram_user_id}
    if note:
        details["note"] = note
    write_audit(
        db=db,
        staff_user_id=None,
        action="offer.approve" if approve else "offer.reject",
        entity="seller_offers",
        entity_id=str(offer.id),
        details=details,
    )
    logger.info(
        "offer_service.moderate_via_telegram",
        extra={"offer_id": offer.id, "approve": approve, "telegram_user_id": telegram_user_id},
    )
    return offer


def enqueue_offer_group_notify(offer_id: int, *, edited: bool = False) -> None:
    """Post an offer to the team Telegram group for moderation, fail-soft.

    Used both for a newly-submitted offer and for one re-entering moderation after a
    seller edit (``edited=True`` → the group message is framed as an update). Skips
    entirely when REQUEST_NOTIFY_CHAT_ID is unset; a broker outage must never break
    offer creation/edit (mirror of request_service._enqueue_group_notify_soft).
    """
    from app.core.config import settings  # noqa: PLC0415

    if settings.REQUEST_NOTIFY_CHAT_ID is None:
        return
    from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

    try:
        send_offer_to_group.apply_async(
            args=[offer_id], kwargs={"edited": edited}, queue="notify", retry=False
        )
    except Exception as exc:  # noqa: BLE001 — broker outage must not break creation
        logger.warning(
            "offer group-notify enqueue failed (broker unavailable); offer %s committed "
            "without a team notification: %s",
            offer_id,
            exc,
        )
