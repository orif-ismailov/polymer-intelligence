"""
Sample requests (P6 W3 — T3.1, FR-L3).

A buyer asks a seller for a physical sample of an offer; the seller accepts and
ships it; the buyer says whether it arrived and whether it was any good.

    requested ─accepted(seller)─► accepted ─sent(seller)─► sent ─received(buyer)─►
        └──────declined(seller)─► declined                  └─rejected_by_buyer(buyer)─►

Both sides drive this machine, which is why `_ACTOR_RULES` is a table and not a
comment. The two moves it exists to prevent:

  * a **seller** marking a parcel `received` — closing their own dispute;
  * a **buyer** marking it `sent` — inventing a shipment.

Three more rules:

  * the offer must actually offer samples (`samples_available`) and must be a
    portal company's: a Telegram seller has no account to accept with;
  * one LIVE request per (offer, buyer) — enforced by a partial unique index, so
    a declined request frees the slot rather than locking the buyer out;
  * shipping requires a courier and a tracking reference. "It's on its way" with
    nothing to track is not a shipment.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.domains.accounts.models import UserAccount
from app.domains.companies.models import Company
from app.domains.lab_orders.models import SampleRequest
from app.domains.marketplace.models import SellerOffer
from app.models.enums import SampleRequestStatus, SellerOfferStatus
from app.services import (
    audit_service,
    event_service,
    event_types,
    notification_service,
)

logger = logging.getLogger(__name__)


# ── State machine (data) ──────────────────────────────────────────────────────

_TRANSITIONS: dict[SampleRequestStatus, set[SampleRequestStatus]] = {
    # The seller has NOT been told yet — the buyer's commitment letter is still
    # unsigned (P7.a W8). Signing it is what moves the request to `requested`, and
    # that move is made by the letter service, not by `transition()`: there is no
    # actor rule for it because it is not a party decision, it is a signature.
    SampleRequestStatus.pending_letter: {SampleRequestStatus.requested},
    SampleRequestStatus.requested: {
        SampleRequestStatus.accepted,
        SampleRequestStatus.declined,
    },
    SampleRequestStatus.accepted: {SampleRequestStatus.sent},
    SampleRequestStatus.sent: {
        SampleRequestStatus.received,
        SampleRequestStatus.rejected_by_buyer,
    },
    # Terminal. Asking again is a NEW request — which is exactly what the partial
    # unique index frees the slot for.
    SampleRequestStatus.declined: set(),
    SampleRequestStatus.received: set(),
    SampleRequestStatus.rejected_by_buyer: set(),
}

#: Which party may make each move. The seller runs the shipment, the buyer runs
#: the receipt; neither speaks for the other.
_ACTOR_RULES: dict[SampleRequestStatus, str] = {
    SampleRequestStatus.accepted: "seller",
    SampleRequestStatus.declined: "seller",
    SampleRequestStatus.sent: "seller",
    SampleRequestStatus.received: "buyer",
    SampleRequestStatus.rejected_by_buyer: "buyer",
}

#: Saying no is a decision the other side has to be able to read.
REASON_REQUIRED: frozenset[SampleRequestStatus] = frozenset(
    {SampleRequestStatus.declined, SampleRequestStatus.rejected_by_buyer}
)

#: FR-L3 — the seller states quantity, courier and tracking number on dispatch.
SHIPMENT_REQUIRED: frozenset[SampleRequestStatus] = frozenset({SampleRequestStatus.sent})


def can_transition(frm: SampleRequestStatus, to: SampleRequestStatus) -> bool:
    return to in _TRANSITIONS[frm]


def actor_for(to: SampleRequestStatus) -> str | None:
    """'buyer' / 'seller' — who is allowed to make this move."""
    return _ACTOR_RULES.get(to)


def available_transitions(
    frm: SampleRequestStatus, role: str
) -> list[SampleRequestStatus]:
    """What this party may do right now, in enum order.

    The portal renders each side's buttons from this, so neither side is offered
    a move the API would refuse.
    """
    return [
        status
        for status in SampleRequestStatus
        if status in _TRANSITIONS[frm] and _ACTOR_RULES.get(status) == role
    ]


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class SamplesNotAvailable(Exception):
    """This offer does not offer samples (or cannot: no portal seller behind it)."""


class OwnOfferSample(Exception):
    """A company cannot request a sample of its own offer."""


class SampleRequestExists(Exception):
    """This buyer already has a live request against this offer."""


class InvalidSampleTransition(Exception):
    """The requested sample-request transition is not allowed."""


class ActorNotAllowed(Exception):
    """This party may not make that move."""


class ReasonRequired(Exception):
    """Declining or rejecting a sample requires a reason."""


class ShipmentDetailsRequired(Exception):
    """Marking a sample sent requires a courier and a tracking reference."""


class NotSampleParty(Exception):
    """The company is neither the buyer nor the seller of this request."""


# ── Lookups ───────────────────────────────────────────────────────────────────


def get(db: Session, request_id: int) -> SampleRequest | None:
    return db.get(SampleRequest, request_id)


def list_for_company(db: Session, company_id: int, *, side: str) -> list[SampleRequest]:
    """`side='incoming'` — requests to answer; `'sent'` — requests we made."""
    column = (
        SampleRequest.seller_company_id
        if side == "incoming"
        else SampleRequest.buyer_company_id
    )
    return (
        db.query(SampleRequest)
        .filter(column == company_id)
        .order_by(SampleRequest.id.desc())
        .all()
    )


def acting_role(sample: SampleRequest, company_id: int) -> str:
    """'buyer' / 'seller' for a party, else NotSampleParty."""
    role = sample.party_role(company_id)
    if role is None:
        raise NotSampleParty(str(company_id))
    return role


# ── Creating ──────────────────────────────────────────────────────────────────


def request(
    db: Session,
    *,
    offer: SellerOffer,
    buyer_company: Company,
    account: UserAccount,
    delivery_address: str,
    qty: str | None = None,
) -> SampleRequest:
    """Ask for a sample. Does NOT commit.

    The seller company is copied onto the row rather than followed through the
    offer: the seller's inbox is queried by that column, and following the offer
    would make the inbox depend on the offer never being edited.
    """
    if not offer.samples_available or offer.status != SellerOfferStatus.approved:
        raise SamplesNotAvailable(str(offer.id))
    if offer.company_id is None:
        # A Telegram-origin offer has no portal account behind it, so there is
        # nobody who could accept the request or enter a tracking number.
        raise SamplesNotAvailable(str(offer.id))
    if offer.company_id == buyer_company.id:
        raise OwnOfferSample(str(offer.id))

    address = (delivery_address or "").strip()
    if not address:
        raise ValueError("delivery_address is required")

    sample = SampleRequest(
        offer_id=offer.id,
        buyer_company_id=buyer_company.id,
        seller_company_id=offer.company_id,
        created_by_user_account_id=account.id,
        delivery_address=address,
        qty=(qty or "").strip() or None,
        # An offer that demands a commitment letter holds the request BEFORE the
        # seller ever sees it: `pending_letter` is not a draft, it is "asked, but
        # not yet undertaken". Signing the letter is what releases it.
        status=(
            SampleRequestStatus.pending_letter
            if offer.sample_letter_required
            else SampleRequestStatus.requested
        ),
    )
    # The partial unique index IS the "one live request" rule. Inserting inside a
    # savepoint so a lost race resolves to a typed error instead of poisoning the
    # caller's transaction (the pattern `escrow_service.record_provider_event`
    # established).
    try:
        with db.begin_nested():
            db.add(sample)
            db.flush()
    except IntegrityError as exc:
        raise SampleRequestExists(str(offer.id)) from exc

    event_service.emit(
        db,
        event_types.SAMPLE_REQUEST_CREATED,
        "sample_request",
        sample.id,
        _payload(sample),
    )
    audit_service.write_audit(
        db, None, "sample_request.create", "sample_requests", str(sample.id),
        {
            "offer_id": offer.id,
            "buyer_company_id": buyer_company.id,
            "seller_company_id": sample.seller_company_id,
            "account_id": account.id,
        },
    )
    # Only tell the seller once it is a real request. A `pending_letter` row is an
    # intention the buyer has not signed yet, and a notification for it would have
    # the seller chasing a request that may never arrive.
    if sample.status != SampleRequestStatus.pending_letter:
        _notify(db, sample, notification_service.KIND_SAMPLE_REQUEST_NEW, to="seller")
    logger.info(
        "sample_service.request",
        extra={"sample_id": sample.id, "offer_id": offer.id, "buyer": buyer_company.id},
    )
    return sample


# ── Moving ────────────────────────────────────────────────────────────────────


def transition(
    db: Session,
    sample: SampleRequest,
    to_status: SampleRequestStatus,
    *,
    acting_company_id: int,
    reason: str | None = None,
    qty: str | None = None,
    courier: str | None = None,
    tracking_ref: str | None = None,
) -> SampleRequest:
    """Move a request, as one of its two parties. Does NOT commit."""
    role = acting_role(sample, acting_company_id)
    frm = sample.status

    if not can_transition(frm, to_status):
        raise InvalidSampleTransition(f"{frm} → {to_status}")
    if _ACTOR_RULES.get(to_status) != role:
        raise ActorNotAllowed(f"{role} may not drive {frm} → {to_status}")

    clean_reason = (reason or "").strip() or None
    if to_status in REASON_REQUIRED and clean_reason is None:
        raise ReasonRequired(str(to_status))

    if to_status in SHIPMENT_REQUIRED:
        clean_courier = (courier or "").strip() or None
        clean_tracking = (tracking_ref or "").strip() or None
        if clean_courier is None or clean_tracking is None:
            raise ShipmentDetailsRequired(str(sample.id))
        sample.courier = clean_courier
        sample.tracking_ref = clean_tracking
        if qty and qty.strip():
            sample.qty = qty.strip()

    sample.status = to_status
    if to_status in REASON_REQUIRED:
        sample.decline_reason = clean_reason
    _stamp(sample, to_status)
    db.flush()

    event_service.emit(
        db,
        event_types.SAMPLE_REQUEST_STATUS_CHANGED,
        "sample_request",
        sample.id,
        _payload(sample, extra={"from": frm.value}),
    )
    audit_service.write_audit(
        db, None, "sample_request.transition", "sample_requests", str(sample.id),
        {
            "from": frm.value,
            "to": to_status.value,
            "by_company_id": acting_company_id,
            "role": role,
            "reason": clean_reason,
        },
    )
    # The party who did NOT act is the one who needs to hear about it.
    _notify(
        db,
        sample,
        notification_service.KIND_SAMPLE_REQUEST_STATUS,
        to="buyer" if role == "seller" else "seller",
        status=to_status.value,
    )
    logger.info(
        "sample_service.transition",
        extra={"sample_id": sample.id, "from": frm.value, "to": to_status.value},
    )
    return sample


def _stamp(sample: SampleRequest, to_status: SampleRequestStatus) -> None:
    """Three timestamps instead of a history table — the machine is short."""
    now = utcnow()
    if to_status is SampleRequestStatus.accepted:
        sample.accepted_at = now
    elif to_status is SampleRequestStatus.sent:
        sample.sent_at = now
    elif to_status is SampleRequestStatus.received:
        sample.received_at = now


# ── Notifications / payloads ──────────────────────────────────────────────────


def _notify(
    db: Session, sample: SampleRequest, kind: str, *, to: str, **extra: object
) -> None:
    """Ring one side's bell.

    `dedup=False`, like the escrow notifications: "your sample was accepted" and
    "your sample was shipped" are different sentences about the same request, and
    the default unread-dedup would swallow the second.
    """
    company_id = (
        sample.seller_company_id if to == "seller" else sample.buyer_company_id
    )
    title_key, body_key = notification_service.keys_for(kind)
    params: dict[str, object] = {
        "sample_id": sample.id,
        "offer_id": sample.offer_id,
    }
    params.update(extra)
    notification_service.notify_company(
        db,
        company_id,
        kind=kind,
        title_key=title_key,
        body_key=body_key,
        params=params,
        entity="sample_request",
        entity_id=str(sample.id),
        dedup=False,
    )


def _payload(
    sample: SampleRequest, *, extra: dict[str, object] | None = None
) -> dict[str, object]:
    body: dict[str, object] = {
        "sample_id": sample.id,
        "offer_id": sample.offer_id,
        "buyer_company_id": sample.buyer_company_id,
        "seller_company_id": sample.seller_company_id,
        "status": sample.status.value,
    }
    body.update(extra or {})
    return body
