"""
Offer-request service — the admin-gated "Request an offer" brokerage flow.

A buyer submits an inquiry against a specific approved seller offer. The inquiry
lands in `pending` for staff review (dashboard queue + team-group buttons). On
approval it is forwarded to the seller by bot DM — WITHOUT the buyer's contact, so
the team stays the intermediary (buyer contact is shown only to staff, seller
contact is no longer shown to the buyer).

Service axiom (DEC-dep-owns-commit): functions call db.flush() to obtain ids but
NEVER commit — the router/handler owns the transaction and post-commit dispatch.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import OfferRequestStatus, SellerOfferStatus
from app.models.marketplace import OfferRequest, SellerOffer
from app.models.requests import Client
from app.schemas.marketplace import (
    AdminOfferRequestBuyer,
    AdminOfferRequestOut,
    AdminOfferRequestSeller,
    OfferBrief,
    OfferRequestCreate,
)
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def create_offer_request(
    db: Session, client: Client, offer_id: int, data: OfferRequestCreate
) -> OfferRequest:
    """Create a `pending` inquiry against an approved offer. Does NOT commit.

    Raises ValueError if the offer does not exist or is not public (approved) — a
    buyer can only inquire on offers actually visible in the catalog.
    """
    offer: SellerOffer | None = db.query(SellerOffer).filter(SellerOffer.id == offer_id).first()
    if offer is None or offer.status != SellerOfferStatus.approved:
        raise ValueError("Offer not found")

    req = OfferRequest(
        offer_id=offer.id,
        client_id=client.id,
        quantity=data.quantity,
        qty_unit=data.qty_unit,
        target_price=data.target_price,
        currency=data.currency,
        message=data.message.strip() if data.message else None,
        status=OfferRequestStatus.pending,
    )
    db.add(req)
    db.flush()
    logger.info(
        "offer_request_service.create",
        extra={"offer_request_id": req.id, "offer_id": offer.id, "client_id": client.id},
    )
    return req


def list_pending(db: Session) -> list[OfferRequest]:
    """Pending inquiries for the dashboard review queue, oldest first."""
    return (
        db.query(OfferRequest)
        .filter(OfferRequest.status == OfferRequestStatus.pending)
        .order_by(OfferRequest.created_at.asc())
        .all()
    )


def get_offer_request(db: Session, offer_request_id: int) -> OfferRequest | None:
    """Return an inquiry by id (any status)."""
    return db.query(OfferRequest).filter(OfferRequest.id == offer_request_id).first()


def list_for_client(db: Session, client_id: int) -> list[OfferRequest]:
    """A buyer's own inquiries, newest first (any status)."""
    return (
        db.query(OfferRequest)
        .filter(OfferRequest.client_id == client_id)
        .order_by(OfferRequest.created_at.desc())
        .all()
    )


def _apply_decision(req: OfferRequest, *, approve: bool, note: str | None) -> None:
    """Shared state transition for a moderation decision (no audit, no commit)."""
    now = utcnow()
    req.status = OfferRequestStatus.approved if approve else OfferRequestStatus.rejected
    req.moderation_note = note
    req.reviewed_at = now
    if approve:
        req.forwarded_at = now


def moderate_offer_request(
    db: Session,
    req: OfferRequest,
    staff_user_id: int,
    *,
    approve: bool,
    note: str | None = None,
) -> OfferRequest:
    """Approve/reject an inquiry from the dashboard. Does NOT commit.

    Approval marks it forwarded; the router enqueues the seller DM after commit.
    """
    _apply_decision(req, approve=approve, note=note)
    req.moderated_by = staff_user_id
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="offer_request.approve" if approve else "offer_request.reject",
        entity="offer_requests",
        entity_id=str(req.id),
        details={"note": note} if note else {},
    )
    logger.info(
        "offer_request_service.moderate",
        extra={"offer_request_id": req.id, "approve": approve, "staff_user_id": staff_user_id},
    )
    return req


def moderate_offer_request_via_telegram(
    db: Session,
    req: OfferRequest,
    telegram_user_id: int,
    *,
    approve: bool,
    note: str | None = None,
) -> OfferRequest:
    """Approve/reject an inquiry from the team Telegram group. Does NOT commit.

    Actor is a group admin (a Telegram user, not a StaffUser): moderated_by stays
    NULL and the acting id is recorded in the audit details.
    """
    _apply_decision(req, approve=approve, note=note)
    db.flush()
    details: dict[str, object] = {"via": "telegram", "telegram_user_id": telegram_user_id}
    if note:
        details["note"] = note
    write_audit(
        db=db,
        staff_user_id=None,
        action="offer_request.approve" if approve else "offer_request.reject",
        entity="offer_requests",
        entity_id=str(req.id),
        details=details,
    )
    logger.info(
        "offer_request_service.moderate_via_telegram",
        extra={"offer_request_id": req.id, "approve": approve, "telegram_user_id": telegram_user_id},
    )
    return req


def to_admin_out(req: OfferRequest) -> AdminOfferRequestOut:
    """Build the staff-facing view (both parties' contacts) from a loaded inquiry."""
    seller = req.offer.seller
    return AdminOfferRequestOut(
        id=req.id,
        status=req.status,
        quantity=req.quantity,
        qty_unit=req.qty_unit,
        target_price=req.target_price,
        currency=req.currency,
        message=req.message,
        created_at=req.created_at,
        offer=OfferBrief.model_validate(req.offer),
        buyer=AdminOfferRequestBuyer.model_validate(req.client),
        seller=AdminOfferRequestSeller.model_validate(seller),
    )


def enqueue_offer_request_to_group(offer_request_id: int) -> None:
    """Post a new inquiry to the team group for review, fail-soft.

    Skips when REQUEST_NOTIFY_CHAT_ID is unset; a broker outage must never break
    inquiry creation.
    """
    from app.core.config import settings  # noqa: PLC0415

    if settings.REQUEST_NOTIFY_CHAT_ID is None:
        return
    from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

    try:
        send_offer_request_to_group.apply_async(
            args=[offer_request_id], queue="notify", retry=False
        )
    except Exception as exc:  # noqa: BLE001 — broker outage must not break creation
        logger.warning(
            "offer-request group-notify enqueue failed; inquiry %s committed without a "
            "team notification: %s",
            offer_request_id,
            exc,
        )


def enqueue_offer_request_to_seller(offer_request_id: int) -> None:
    """Forward an approved inquiry to the seller by bot DM, fail-soft.

    Called after the approval transaction commits (dashboard or group). A broker/bot
    outage must never break the approval.
    """
    from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

    try:
        send_offer_request_to_seller.apply_async(
            args=[offer_request_id], queue="notify", retry=False
        )
    except Exception as exc:  # noqa: BLE001 — bot/broker outage must not break approval
        logger.warning(
            "offer-request seller-forward enqueue failed for inquiry %s: %s",
            offer_request_id,
            exc,
        )
