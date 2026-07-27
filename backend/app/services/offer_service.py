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
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.time import utcnow
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.enums import (
    CompanyStatus,
    OfferAvailability,
    OfferFileKind,
    SellerOfferStatus,
)
from app.models.marketplace import OfferFavorite, Seller, SellerOffer, SellerOfferFile
from app.models.reference import Product, ProductSynonym
from app.schemas.marketplace import CategoryCount, SellerOfferCreate, SellerOfferUpdate
from app.schemas.portal_company import CompanyOfferIn
from app.services import event_service, event_types, notification_service
from app.services.audit_service import write_audit
from app.services.relevance_service import normalize_term

logger = logging.getLogger(__name__)


class CompanyNotVerified(Exception):
    """A company may only publish offers once it is verified."""


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


def matching_product_ids(db: Session, q: str) -> list[int]:
    """Product ids whose code, any localized name, or a synonym matches ``q``.

    Bridges cross-language catalog search. A seller may list an offer under the Latin
    product code ("PP") while a buyer searches with the Cyrillic abbreviation ("ПП") or a
    full name in any supported language. This resolves the term to product ids via:

    - the ``products`` table: ``code`` + every localized name column (ru/uz/en/tr), so a
      full or partial name in any of those languages matches; and
    - the ``product_synonyms`` dictionary (same table the UZEX relevance filter uses), so
      abbreviations like "ПП", "ПЭВД", "ПНД" — which are NOT substrings of the full name —
      still resolve to the right product.

    The caller ORs the result into the catalog query as ``product_id IN (...)`` alongside
    the offer's own free-text columns, so nothing that matched before stops matching.
    """
    term = q.strip()
    if not term:
        return []

    like = f"%{term}%"
    ids: set[int] = {
        pid
        for (pid,) in db.query(Product.id).filter(
            or_(
                Product.code.ilike(like),
                Product.name_ru.ilike(like),
                Product.name_uz.ilike(like),
                Product.name_en.ilike(like),
                Product.name_tr.ilike(like),
            )
        )
    }

    # Synonym dictionary: normalized (case/space-insensitive) partial match so a bare
    # abbreviation resolves. `synonym_norm` was seeded via the same normalize_term, so
    # the normalization is symmetric. Skip 1-char terms — too noisy to be useful.
    norm = normalize_term(term)
    if len(norm) >= 2:
        ids.update(
            pid
            for (pid,) in db.query(ProductSynonym.product_id).filter(
                ProductSynonym.synonym_norm.ilike(f"%{norm}%")
            )
        )
    return list(ids)


def list_catalog(
    db: Session,
    *,
    product_id: int | None = None,
    q: str | None = None,
    availability: OfferAvailability | None = None,
    country: str | None = None,
    exclude_seller_id: int | None = None,
    exclude_company_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SellerOffer]:
    """Public catalog: approved offers, optionally filtered by product / free-text.

    Free-text ``q`` matches the offer's own columns (product_text/grade_text/polymer_type)
    AND resolves through :func:`matching_product_ids`, so a search in any supported
    language — including a Cyrillic abbreviation like "ПП" for a "PP"-coded offer — returns
    the linked catalog offers.

    ``availability`` / ``country`` are optional equality filters (R2 portal market).

    When ``exclude_seller_id`` is set, that seller's own listings are omitted — a seller
    browsing the marketplace sees only other sellers' offers (they manage their own under
    "My offers" and cannot inquire on them). ``exclude_company_id`` does the same for a
    portal company browsing the market (it can't inquire on its own offers).
    """
    # Eager-load the company AND its roles: the card renders both, and the market
    # list is the busiest screen in the portal — a lazy relationship here is one
    # SELECT per card.
    query = (
        db.query(SellerOffer)
        .options(
            joinedload(SellerOffer.company).selectinload(Company.business_roles),
            selectinload(SellerOffer.files),
        )
        .filter(SellerOffer.status == SellerOfferStatus.approved)
    )
    if exclude_seller_id is not None:
        query = query.filter(SellerOffer.seller_id != exclude_seller_id)
    if exclude_company_id is not None:
        query = query.filter(
            or_(
                SellerOffer.company_id.is_(None),
                SellerOffer.company_id != exclude_company_id,
            )
        )
    if product_id is not None:
        query = query.filter(SellerOffer.product_id == product_id)
    if availability is not None:
        query = query.filter(SellerOffer.availability == availability)
    if country is not None:
        query = query.filter(SellerOffer.country == country)
    if q:
        like = f"%{q.strip()}%"
        conditions = [
            SellerOffer.product_text.ilike(like),
            SellerOffer.grade_text.ilike(like),
            SellerOffer.polymer_type.ilike(like),
        ]
        product_ids = matching_product_ids(db, q)
        if product_ids:
            conditions.append(SellerOffer.product_id.in_(product_ids))
        query = query.filter(or_(*conditions))
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


def _notify_company_offer_moderated(
    db: Session, offer: SellerOffer, *, approve: bool
) -> None:
    """Notify a company-origin offer's members of a moderation outcome (R2 A2).

    Flush-only, in the moderation transaction. No-op for TG-seller offers (their
    seller learns the outcome through the existing TG surface). ``dedup=False`` so a
    re-moderation after a seller edit re-notifies.
    """
    if offer.company_id is None:
        return
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_OFFER_MODERATED
    )
    notification_service.notify_company(
        db,
        offer.company_id,
        kind=notification_service.KIND_OFFER_MODERATED,
        title_key=title_key,
        body_key=body_key,
        params={"offer_id": offer.id, "outcome": "approved" if approve else "rejected"},
        entity="offer",
        entity_id=str(offer.id),
        dedup=False,
    )


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
    _notify_company_offer_moderated(db, offer, approve=approve)

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
    _notify_company_offer_moderated(db, offer, approve=approve)

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


# ── Company-origin offers (R1 W5 — portal) ────────────────────────────────────


def create_company_offer(
    db: Session, company: Company, account: UserAccount, data: CompanyOfferIn
) -> SellerOffer:
    """Publish an offer on behalf of a VERIFIED company (seller_id NULL, company_id set).

    Enters the SAME `pending_moderation` machine as seller offers — no lifecycle
    changes. Raises CompanyNotVerified if the company isn't verified yet. Does NOT
    commit; also emits OFFER_PUBLISHED_BY_COMPANY.
    """
    if company.status != CompanyStatus.verified:
        raise CompanyNotVerified(str(company.status))

    offer = SellerOffer(
        seller_id=None,
        company_id=company.id,
        created_by_user_account_id=account.id,
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
        lead_time_days=data.lead_time_days,
        sale_mode=data.sale_mode,
        accepts_rfq=data.accepts_rfq,
        accepts_contract=data.accepts_contract,
        accepts_escrow=data.accepts_escrow,
        status=SellerOfferStatus.pending_moderation,
    )
    db.add(offer)
    db.flush()
    event_service.emit(
        db, event_types.OFFER_PUBLISHED_BY_COMPANY, "seller_offer", offer.id,
        {"company_id": company.id, "account_id": account.id},
    )
    write_audit(
        db, None, "offer.create", "seller_offers", str(offer.id),
        {"via": "company", "company_id": company.id, "account_id": account.id},
    )
    logger.info("offer_service.create_company", extra={"offer_id": offer.id, "company_id": company.id})
    return offer


def update_company_offer(
    db: Session, offer: SellerOffer, data: CompanyOfferIn
) -> tuple[SellerOffer, bool]:
    """Full-replacement edit of a company offer; an approved/rejected offer re-enters
    moderation (mirror of update_offer). Returns (offer, requeued). Does NOT commit.
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
    offer.lead_time_days = data.lead_time_days
    offer.sale_mode = data.sale_mode
    offer.accepts_rfq = data.accepts_rfq
    offer.accepts_contract = data.accepts_contract
    offer.accepts_escrow = data.accepts_escrow

    requeued = offer.status in (SellerOfferStatus.approved, SellerOfferStatus.rejected)
    if requeued:
        offer.status = SellerOfferStatus.pending_moderation
        offer.published_at = None
        offer.moderated_by = None
        offer.moderation_note = None

    db.flush()
    write_audit(
        db, None, "offer.edit", "seller_offers", str(offer.id),
        {"via": "company", "requeued": requeued},
    )
    logger.info(
        "offer_service.update_company",
        extra={"offer_id": offer.id, "company_id": offer.company_id, "requeued": requeued},
    )
    return offer, requeued


# ── Offer photos (P1 W3 — T3.1) ───────────────────────────────────────────────


class TooManyPhotos(Exception):
    """The offer already holds MAX_OFFER_IMAGES photos."""


def count_offer_images(db: Session, offer_id: int) -> int:
    """Photos currently attached to the offer (documents don't count)."""
    return int(
        db.query(SellerOfferFile)
        .filter(
            SellerOfferFile.offer_id == offer_id,
            SellerOfferFile.kind == OfferFileKind.image,
        )
        .count()
    )


def offer_images(db: Session, offer_id: int) -> list[SellerOfferFile]:
    """Photos in display order — upload order (id ASC); the first one is the cover."""
    return (
        db.query(SellerOfferFile)
        .filter(
            SellerOfferFile.offer_id == offer_id,
            SellerOfferFile.kind == OfferFileKind.image,
        )
        .order_by(SellerOfferFile.id)
        .all()
    )


def cover_file_id(db: Session, offer_id: int) -> int | None:
    """Id of the cover photo (the first uploaded), or None when there are none."""
    first = (
        db.query(SellerOfferFile.id)
        .filter(
            SellerOfferFile.offer_id == offer_id,
            SellerOfferFile.kind == OfferFileKind.image,
        )
        .order_by(SellerOfferFile.id)
        .first()
    )
    return int(first[0]) if first else None


def requeue_for_photo_change(db: Session, offer: SellerOffer) -> bool:
    """Send a live offer back to moderation because its photos changed (FR-M2).

    Photos are part of what moderation approved, so changing them on an approved (or
    rejected) offer re-enters the queue — the same rule `update_company_offer` applies
    to field edits. A draft or already-pending offer is untouched. Does NOT commit.
    """
    if offer.status not in (SellerOfferStatus.approved, SellerOfferStatus.rejected):
        return False

    offer.status = SellerOfferStatus.pending_moderation
    offer.published_at = None
    offer.moderated_by = None
    offer.moderation_note = None
    db.flush()
    write_audit(
        db, None, "offer.photos_changed", "seller_offers", str(offer.id),
        {"via": "company", "requeued": True},
    )
    logger.info(
        "offer_service.requeue_for_photo_change",
        extra={"offer_id": offer.id, "company_id": offer.company_id},
    )
    return True


def list_company_offers(db: Session, company_id: int) -> list[SellerOffer]:
    """All offers (any status) published by a company, newest first."""
    return (
        db.query(SellerOffer)
        .filter(SellerOffer.company_id == company_id)
        .order_by(SellerOffer.created_at.desc())
        .all()
    )


# ── Favorites (P4 W1 — T1.2) ──────────────────────────────────────────────────
#
# A shortlist is personal: it hangs off the ACCOUNT, not the company, so someone
# switching company hats in the portal keeps their own list.


def add_favorite(db: Session, account_id: int, offer_id: int) -> bool:
    """Star an offer. Returns True when a row was created, False when it was
    already starred. Does NOT commit.

    Idempotent by design — a double tap on the heart, or a retried request, must
    not 500 on the unique constraint. The INSERT runs inside a SAVEPOINT so a
    losing race raises IntegrityError without poisoning the caller's transaction.
    """
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    existing = (
        db.query(OfferFavorite.id)
        .filter(
            OfferFavorite.user_account_id == account_id,
            OfferFavorite.offer_id == offer_id,
        )
        .first()
    )
    if existing is not None:
        return False
    try:
        with db.begin_nested():
            db.add(OfferFavorite(user_account_id=account_id, offer_id=offer_id))
            db.flush()
    except IntegrityError:
        return False
    return True


def remove_favorite(db: Session, account_id: int, offer_id: int) -> bool:
    """Unstar an offer. Returns True when a row was deleted. Does NOT commit.

    Removing something that was never starred is a no-op, not an error: the
    client's intent ("this should not be in my list") is already satisfied.
    """
    deleted = (
        db.query(OfferFavorite)
        .filter(
            OfferFavorite.user_account_id == account_id,
            OfferFavorite.offer_id == offer_id,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return bool(deleted)


def favorite_offer_ids(db: Session, account_id: int, offer_ids: list[int]) -> set[int]:
    """Which of `offer_ids` this account has starred — one query for a whole page.

    Resolved server-side so the heart is filled on first paint; the alternative is
    a second round trip per card.
    """
    if not offer_ids:
        return set()
    rows = db.query(OfferFavorite.offer_id).filter(
        OfferFavorite.user_account_id == account_id,
        OfferFavorite.offer_id.in_(offer_ids),
    )
    return {offer_id for (offer_id,) in rows}


def list_favorites(db: Session, account_id: int) -> list[SellerOffer]:
    """The account's starred offers, most recently starred first.

    Only APPROVED offers come back: an offer pulled from the catalog (archived,
    or sent back to moderation after an edit) must not resurface here as if it
    were still on sale.
    """
    return (
        db.query(SellerOffer)
        .join(OfferFavorite, OfferFavorite.offer_id == SellerOffer.id)
        .filter(
            OfferFavorite.user_account_id == account_id,
            SellerOffer.status == SellerOfferStatus.approved,
        )
        .order_by(OfferFavorite.id.desc())
        .all()
    )
