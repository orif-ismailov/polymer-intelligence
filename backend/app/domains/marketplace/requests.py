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

import decimal
import logging

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.domains.accounts.models import UserAccount
from app.domains.companies.models import Company
from app.domains.marketplace.models import OfferRequest, SellerOffer
from app.domains.marketplace.schemas import (
    AdminOfferRequestBuyer,
    AdminOfferRequestCompany,
    AdminOfferRequestOut,
    AdminOfferRequestSeller,
    OfferBrief,
    OfferRequestCreate,
    OfferRequestUpdate,
)
from app.domains.requests.models import Client
from app.models.enums import OfferRequestStatus, SellerOfferStatus
from app.services import notification_service
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)

# Logical fields shown in the buyer-edit diff (rendered in the group + seller messages).
_DIFF_FIELDS = ("quantity", "target_price", "message")


class AlreadyModerated(Exception):
    """The inquiry has already left `pending` — another decision won the race.

    Carries the status the winning decision left, so the caller can tell a
    moderator what actually happened to the item they were acting on.
    """

    def __init__(self, offer_request_id: int, current_status: str) -> None:
        super().__init__(f"inquiry {offer_request_id} is already {current_status}")
        self.offer_request_id = offer_request_id
        self.current_status = current_status


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

    # A seller cannot inquire on its own listing — buyer and seller are the same Telegram
    # identity. Enforced server-side (the UI also hides "Request an offer" via is_own).
    seller = offer.seller
    client_tg = client.telegram_user_id
    if seller is not None and client_tg is not None and seller.telegram_user_id == client_tg:
        raise ValueError("You cannot send an inquiry on your own offer")

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


def create_company_inquiry(
    db: Session,
    company: Company,
    account: UserAccount,
    offer: SellerOffer,
    data: OfferRequestCreate,
) -> OfferRequest:
    """Create a `pending` company-origin inquiry against an approved offer (R2 A2).

    Mirrors ``create_offer_request`` but carries ``company_id`` +
    ``created_by_user_account_id`` (``client_id`` NULL). Enters the SAME moderation
    machine — staff review it identically to TG inquiries. Does NOT commit.

    Raises ValueError if the offer is not public (approved) or if the buyer company
    is the seller of the offer (a company cannot inquire on its own listing).
    """
    if offer.status != SellerOfferStatus.approved:
        raise ValueError("Offer not found")

    if offer.company_id is not None and offer.company_id == company.id:
        raise ValueError("You cannot send an inquiry on your own offer")

    req = OfferRequest(
        offer_id=offer.id,
        client_id=None,
        company_id=company.id,
        created_by_user_account_id=account.id,
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
        "offer_request_service.create_company",
        extra={
            "offer_request_id": req.id,
            "offer_id": offer.id,
            "company_id": company.id,
            "account_id": account.id,
        },
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


def list_for_company(db: Session, company_id: int) -> list[OfferRequest]:
    """Inquiries SENT by a company (portal-origin), newest first (any status)."""
    return (
        db.query(OfferRequest)
        .filter(OfferRequest.company_id == company_id)
        .order_by(OfferRequest.created_at.desc())
        .all()
    )


def list_incoming_for_company(db: Session, company_id: int) -> list[OfferRequest]:
    """Post-moderation inquiries RECEIVED on a company's own offers, newest first.

    Only approved (forwarded) inquiries are visible to the selling company — the
    pending/rejected moderation states stay internal to staff.
    """
    return (
        db.query(OfferRequest)
        .join(SellerOffer, OfferRequest.offer_id == SellerOffer.id)
        .filter(
            SellerOffer.company_id == company_id,
            OfferRequest.status == OfferRequestStatus.approved,
        )
        .order_by(OfferRequest.created_at.desc())
        .all()
    )


def list_company_inquiries_for_offer(
    db: Session, company_id: int, offer_id: int
) -> list[OfferRequest]:
    """A company's own inquiries against one offer (the market-detail relationship block)."""
    return (
        db.query(OfferRequest)
        .filter(
            OfferRequest.company_id == company_id,
            OfferRequest.offer_id == offer_id,
        )
        .order_by(OfferRequest.created_at.desc())
        .all()
    )


def _fmt_num(value: decimal.Decimal | None) -> str | None:
    """Format a Decimal without insignificant trailing zeros (100.000 -> '100')."""
    if value is None:
        return None
    s = f"{value:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _field_displays(
    quantity: decimal.Decimal | None,
    qty_unit: str,
    target_price: decimal.Decimal | None,
    currency: str | None,
    message: str | None,
) -> dict[str, str | None]:
    """Human-readable display strings for the diffable inquiry fields."""
    qty = f"{_fmt_num(quantity)} {qty_unit}" if quantity is not None else None
    price = (
        f"{_fmt_num(target_price)} {currency or ''}".strip()
        if target_price is not None
        else None
    )
    msg = (message or "").strip() or None
    return {"quantity": qty, "target_price": price, "message": msg}


def update_offer_request(
    db: Session, req: OfferRequest, data: OfferRequestUpdate
) -> tuple[OfferRequest, list[dict[str, str | None]]]:
    """Apply a buyer's revision to their own inquiry. Does NOT commit.

    - A rejected inquiry cannot be edited (ValueError).
    - A no-op edit (nothing actually changed) leaves the row untouched and returns [].
    - Otherwise records the edit (edited_at) and accumulates a diff into
      last_change_summary — the net change since the seller last saw the inquiry, so
      several edits before re-approval still show one coherent old->new per field.
    - Editing an already-forwarded (approved) inquiry resets it to `pending` so the
      team re-approves before the seller is shown the new version (re-review policy).

    Returns (req, changes) where `changes` is the accumulated diff (empty on no-op).
    """
    if req.status == OfferRequestStatus.rejected:
        raise ValueError("A rejected inquiry cannot be edited")

    new_message = data.message.strip() if data.message else None

    # Detect real changes on raw values (Decimal equality ignores trailing zeros).
    changed = {
        "quantity": req.quantity != data.quantity or req.qty_unit != data.qty_unit,
        "target_price": req.target_price != data.target_price
        or (req.currency or None) != (data.currency or None),
        "message": (req.message or None) != new_message,
    }
    if not any(changed.values()):
        return req, []

    before = _field_displays(
        req.quantity, req.qty_unit, req.target_price, req.currency, req.message
    )

    req.quantity = data.quantity
    req.qty_unit = data.qty_unit
    req.target_price = data.target_price
    req.currency = data.currency
    req.message = new_message

    after = _field_displays(
        req.quantity, req.qty_unit, req.target_price, req.currency, req.message
    )

    # Accumulate the net diff vs. the last version the seller saw. `old` is preserved
    # from the earliest un-notified edit; a field reverting to its `old` drops out.
    by_field: dict[str, dict[str, str | None]] = {}
    for c in req.last_change_summary or []:
        key = c.get("field")
        if isinstance(key, str):
            by_field[key] = c
    for field in _DIFF_FIELDS:
        if not changed[field]:
            continue
        baseline_old = by_field[field]["old"] if field in by_field else before[field]
        if baseline_old == after[field]:
            by_field.pop(field, None)  # reverted to the last-seen value
        else:
            by_field[field] = {"field": field, "old": baseline_old, "new": after[field]}
    summary = [by_field[f] for f in _DIFF_FIELDS if f in by_field]

    req.edited_at = utcnow()
    req.last_change_summary = summary or None

    # An edit to an already-forwarded inquiry re-enters moderation (re-review policy).
    if req.status == OfferRequestStatus.approved:
        req.status = OfferRequestStatus.pending
        req.reviewed_at = None
        req.moderated_by = None
        req.moderation_note = None

    db.flush()
    write_audit(
        db=db,
        staff_user_id=None,
        action="offer_request.edit",
        entity="offer_requests",
        entity_id=str(req.id),
        details={"via": "buyer", "client_id": req.client_id, "changes": summary},
    )
    logger.info(
        "offer_request_service.update",
        extra={
            "offer_request_id": req.id,
            "client_id": req.client_id,
            "fields": [c["field"] for c in summary],
        },
    )
    return req, summary


def _decision_values(*, approve: bool, note: str | None) -> dict[str, object]:
    """Shared column set for a moderation decision (no audit, no commit)."""
    now = utcnow()
    values: dict[str, object] = {
        "status": OfferRequestStatus.approved if approve else OfferRequestStatus.rejected,
        "moderation_note": note,
        "reviewed_at": now,
    }
    if approve:
        values["forwarded_at"] = now
    return values


def _claim_pending(db: Session, req: OfferRequest, values: dict[str, object]) -> None:
    """Optimistically move an inquiry OUT of `pending`; AlreadyModerated if it left.

    Approve and reject are separate endpoints over the same queue item, so a
    read-then-write leaves room for two moderators to each land half a decision —
    one verdict in `status`, the other's note in `moderation_note`. The
    `WHERE status='pending'` guard makes it exactly-once instead; the loser
    updates 0 rows. Mirror of ``offer_service._claim_pending_moderation``.
    """
    result = db.execute(
        update(OfferRequest)
        .where(
            OfferRequest.id == req.id,
            OfferRequest.status == OfferRequestStatus.pending,
        )
        .values(values)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]  # DML → CursorResult.rowcount
        db.refresh(req)  # report what the winner left, not our stale read
        raise AlreadyModerated(req.id, str(req.status))
    db.refresh(req)


def _forward_on_approval(db: Session, req: OfferRequest) -> None:
    """Notify the *selling* side that an inquiry was approved, routed by offer origin.

    Company-origin offer (R1) → an in-portal notification for every active member of
    the selling company (kind ``inquiry_approved``), written in THIS transaction —
    contact withholding is unchanged (the notification carries only ids, not the
    buyer's identity). TG-seller offer → no-op here; the caller enqueues the existing
    bot-DM forward after commit.

    ``dedup=False`` so a re-approval after a buyer edit always re-notifies the seller.
    """
    offer = req.offer
    if offer.company_id is None:
        return  # TG-seller offer → existing post-commit bot DM handles it
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_INQUIRY_APPROVED
    )
    notification_service.notify_company(
        db,
        offer.company_id,
        kind=notification_service.KIND_INQUIRY_APPROVED,
        title_key=title_key,
        body_key=body_key,
        params={"offer_id": offer.id, "inquiry_id": req.id},
        entity="inquiry",
        entity_id=str(req.id),
        dedup=False,
    )


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
    Raises `AlreadyModerated` when the inquiry is no longer pending — the
    decision is exactly-once, see :func:`_claim_pending`.
    """
    values = _decision_values(approve=approve, note=note)
    values["moderated_by"] = staff_user_id
    _claim_pending(db, req, values)
    if approve:
        _forward_on_approval(db, req)
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
    NULL and the acting id is recorded in the audit details. Shares the dashboard
    path's exactly-once claim — a double-tapped inline button loses the race the
    same way (`AlreadyModerated`).
    """
    _claim_pending(db, req, _decision_values(approve=approve, note=note))
    if approve:
        _forward_on_approval(db, req)
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


def _company_party(company: object | None) -> AdminOfferRequestCompany | None:
    """A company party block (name + verified badge) for the staff queue, or None."""
    if company is None:
        return None
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    return AdminOfferRequestCompany(
        id=company.id,  # type: ignore[attr-defined]
        name=company.short_name or company.legal_name,  # type: ignore[attr-defined]
        verified=company.status == CompanyStatus.verified,  # type: ignore[attr-defined]
    )


def to_admin_out(req: OfferRequest) -> AdminOfferRequestOut:
    """Build the staff-facing view (both parties' contacts) from a loaded inquiry.

    Dual-origin (R2 W4): a portal buyer has no ``client`` (→ ``buyer_company``); a
    company-origin offer has no ``seller`` (→ ``seller_company``).
    """
    offer = req.offer
    seller = offer.seller
    return AdminOfferRequestOut(
        id=req.id,
        status=req.status,
        quantity=req.quantity,
        qty_unit=req.qty_unit,
        target_price=req.target_price,
        currency=req.currency,
        message=req.message,
        created_at=req.created_at,
        origin=req.origin,
        offer=OfferBrief.model_validate(offer),
        buyer=AdminOfferRequestBuyer.model_validate(req.client) if req.client is not None else None,
        buyer_company=_company_party(req.company),
        seller=AdminOfferRequestSeller.model_validate(seller) if seller is not None else None,
        seller_company=_company_party(offer.company),
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
