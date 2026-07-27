"""Escrow payment service (R4 / P3 — T1.2). The money side of a deal.

Money never touches this platform: it moves between the buyer, a partner bank
and the seller. What lives here is the *record* of that movement, and the rule
that every recorded movement drags the deal with it —

    escrow pending  ─funded──►  funded  ─released──►  released
         │                        │
         └──refunded──►  refunded ◄┘

    funded   ⇒ deal payment_pending → paid_escrow   (system)
    released ⇒ deal delivered       → completed     (system)
    refunded ⇒ deal …               → cancelled     (staff, reason recorded)

Three invariants hold this together:

  * **One transaction.** The escrow row and the deal move together or not at
    all. A deal transition that the state machine refuses takes the escrow mark
    down with it — there is a test that funds an escrow, tries to refund it
    without a dispute, and asserts the payment is still `funded` afterwards.
  * **A row lock per mark.** `SELECT … FOR UPDATE` on the payment, so two
    operators clicking at once cannot both transition the deal.
  * **No hand-driven money statuses.** `paid_escrow` and `completed` accept
    `actor_kind=system` only (`deal_service._ACTOR_RULES`), so the only way into
    them is through this module.

FR-D8 shows up here as a refusal: once escrow is funded, a refund needs the deal
disputed first, because `paid_escrow → cancelled` is not a transition. That is
deliberate — it makes a refund a recorded staff decision rather than a quiet
reversal.
"""

from __future__ import annotations

import datetime
import decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.deals import Deal
from app.models.enums import DealActorKind, DealStatus, EscrowStatus
from app.models.payments import ESCROW_MODE_STUB, EscrowPayment, ProviderEvent
from app.models.staff import StaffUser
from app.services import (
    audit_service,
    deal_service,
    event_service,
    event_types,
    notification_service,
)

logger = logging.getLogger(__name__)


# ── State machine (data) ──────────────────────────────────────────────────────

_TRANSITIONS: dict[EscrowStatus, set[EscrowStatus]] = {
    # An invoice was issued. Either the money arrives, or the deal dies and the
    # never-received escrow is closed as refunded.
    EscrowStatus.pending: {EscrowStatus.funded, EscrowStatus.refunded},
    EscrowStatus.funded: {EscrowStatus.released, EscrowStatus.refunded},
    # Terminal: a released or refunded payment is a finished bank operation.
    # Reversing one is a NEW payment, never a status edit.
    EscrowStatus.released: set(),
    EscrowStatus.refunded: set(),
}

#: The deal status each escrow move asserts. Nothing here is optional — an
#: escrow move that did not touch the deal would let the two drift apart.
_DEAL_EFFECT: dict[EscrowStatus, DealStatus] = {
    EscrowStatus.funded: DealStatus.paid_escrow,
    EscrowStatus.released: DealStatus.completed,
    EscrowStatus.refunded: DealStatus.cancelled,
}

#: Column prefixes for the per-move evidence (`funded_at` / `funded_marked_by`).
_STAMPS: dict[EscrowStatus, str] = {
    EscrowStatus.funded: "funded",
    EscrowStatus.released: "released",
    EscrowStatus.refunded: "refunded",
}

#: Marker written into `deals.cancelled_reason` when a refund ends the deal, so
#: a cancellation caused by money is distinguishable from a party walking away.
REFUND_REASON = "escrow_refund"


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class DealAmountMissing(Exception):
    """The deal carries no agreed total, so no invoice can be raised for it."""


class InvalidEscrowTransition(Exception):
    """The requested escrow status transition is not allowed."""


class EscrowReleaseBeforeDelivery(Exception):
    """Funds may only be released once the buyer has confirmed delivery."""


class NoteRequired(Exception):
    """Marking a money movement requires the operator's reference note."""


class StaffRequired(Exception):
    """This mark must be attributed to a staff member (stub rail)."""


# ── Lookups ───────────────────────────────────────────────────────────────────


def for_deal(db: Session, deal_id: int) -> EscrowPayment | None:
    """The deal's escrow payment, if one has been opened."""
    return db.query(EscrowPayment).filter(EscrowPayment.deal_id == deal_id).first()


def available_marks(payment: EscrowPayment) -> list[EscrowStatus]:
    """Statuses this payment may move to right now.

    The dashboard's buttons are built from this, so the UI never offers a mark
    the API would refuse — and never re-implements the machine in TypeScript.
    """
    return [status for status in EscrowStatus if status in _TRANSITIONS[payment.status]]


# ── Opening ───────────────────────────────────────────────────────────────────


def open_for_deal(
    db: Session, deal: Deal, *, mode: str | None = None
) -> EscrowPayment:
    """Raise the escrow for a signed deal and move it to `payment_pending`.

    Called by the `DEAL_STATUS_CHANGED (to=contract_signed)` outbox consumer,
    where delivery is at-least-once — hence idempotent: an existing payment is
    returned untouched, and the deal is not transitioned a second time.

    `mode` is resolved from the runtime setting and then FROZEN on the row: an
    operator may flip the rail later, but a payment opened on the stub rail
    stays a stub payment.

    Raises `DealAmountMissing` when the deal has no agreed total (a deal opened
    from an inquiry may not). The deal then waits at `contract_signed` for staff
    rather than advancing to `payment_pending` with no invoice behind it.
    """
    existing = for_deal(db, deal.id)
    if existing is not None:
        return existing

    if deal.amount is None:
        raise DealAmountMissing(str(deal.id))

    if mode is None:
        from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

        mode = escrow_client.current_mode(db)

    payment = EscrowPayment(
        deal_id=deal.id,
        amount=decimal.Decimal(deal.amount).quantize(decimal.Decimal("0.01")),
        currency=deal.currency,
        status=EscrowStatus.pending,
        mode=mode or ESCROW_MODE_STUB,
    )
    db.add(payment)
    db.flush()

    # The deal follows the invoice. `system` because nothing about this is a
    # human decision — the contract being signed is what caused it.
    deal_service.transition(
        db, deal, DealStatus.payment_pending, actor_kind=DealActorKind.system
    )

    event_service.emit(
        db,
        event_types.ESCROW_OPENED,
        "escrow_payment",
        payment.id,
        _payload(deal, payment),
    )
    audit_service.write_audit(
        db, None, "escrow.open", "escrow_payments", str(payment.id),
        {"deal_id": deal.id, "amount": str(payment.amount), "currency": payment.currency,
         "mode": payment.mode},
    )
    _notify_both(db, deal, payment, notification_service.KIND_ESCROW_OPENED)
    logger.info(
        "escrow_service.open",
        extra={"payment_id": payment.id, "deal_id": deal.id, "mode": payment.mode},
    )
    return payment


# ── Marking a movement ────────────────────────────────────────────────────────


def mark(
    db: Session,
    payment: EscrowPayment,
    to_status: EscrowStatus,
    *,
    staff_user: StaffUser | None,
    note: str,
) -> EscrowPayment:
    """Record that money moved, and move the deal with it.

    On the stub rail `staff_user` is the operator asserting the movement against
    a bank statement; their id and mandatory `note` are the evidence that the
    claim is checkable. (The live rail, P7, supplies the provider event instead
    — see `apply_provider_event`.)

    Order matters: the payment row is locked and stamped first, then the deal is
    transitioned. If the deal's state machine refuses the move, the exception
    propagates and the caller's rollback discards BOTH — an escrow can never
    report money that the deal does not reflect.
    """
    clean_note = (note or "").strip()
    if not clean_note:
        raise NoteRequired(str(payment.id))
    if staff_user is None:
        raise StaffRequired(str(payment.id))

    locked = db.execute(
        select(EscrowPayment).where(EscrowPayment.id == payment.id).with_for_update()
    ).scalar_one()
    frm = locked.status

    if to_status not in _TRANSITIONS[frm]:
        raise InvalidEscrowTransition(f"{frm} → {to_status}")

    deal = db.get(Deal, locked.deal_id)
    if deal is None:  # pragma: no cover — FK guarantees it
        raise InvalidEscrowTransition(f"payment {locked.id} has no deal")

    # The one guard the deal machine cannot express: `delivered → completed` is a
    # valid deal move, but paying the seller out of an escrow whose goods were
    # never confirmed delivered is the failure this feature exists to prevent.
    if to_status is EscrowStatus.released and deal.status != DealStatus.delivered:
        raise EscrowReleaseBeforeDelivery(f"deal is {deal.status.value}")

    now = utcnow()
    stamp = _STAMPS[to_status]
    locked.status = to_status
    setattr(locked, f"{stamp}_at", now)
    setattr(locked, f"{stamp}_marked_by", staff_user.id)
    locked.note = clean_note
    db.flush()

    _drag_the_deal(db, deal, to_status, staff_user, clean_note)

    event_service.emit(
        db,
        _EVENT_FOR[to_status],
        "escrow_payment",
        locked.id,
        _payload(deal, locked, extra={"from": frm.value, "note": clean_note}),
    )
    audit_service.write_audit(
        db, staff_user.id, "escrow.mark", "escrow_payments", str(locked.id),
        {"deal_id": deal.id, "from": frm.value, "to": to_status.value, "note": clean_note},
    )
    _notify_both(
        db, deal, locked, notification_service.KIND_ESCROW_STATUS, status=to_status.value
    )
    logger.info(
        "escrow_service.mark",
        extra={"payment_id": locked.id, "deal_id": deal.id, "to": to_status.value},
    )

    if locked is not payment:
        db.refresh(payment)
    return payment


def _drag_the_deal(
    db: Session,
    deal: Deal,
    to_status: EscrowStatus,
    staff_user: StaffUser,
    note: str,
) -> None:
    """Apply the deal transition this escrow move asserts.

    `funded`/`released` are consequences of an event, so they go in as `system`.
    A refund CANCELS the deal, and a cancel is a decision with a reason — it is
    attributed to the staff member who marked it, and carries the `escrow_refund`
    marker so a money-driven cancellation is distinguishable from a party simply
    walking away.
    """
    target = _DEAL_EFFECT[to_status]
    if to_status is EscrowStatus.refunded:
        deal_service.transition(
            db,
            deal,
            target,
            actor_kind=DealActorKind.staff,
            actor_id=staff_user.id,
            reason=f"{REFUND_REASON}: {note}",
        )
        return
    deal_service.transition(db, deal, target, actor_kind=DealActorKind.system)


_EVENT_FOR: dict[EscrowStatus, str] = {
    EscrowStatus.funded: event_types.ESCROW_FUNDED,
    EscrowStatus.released: event_types.ESCROW_RELEASED,
    EscrowStatus.refunded: event_types.ESCROW_REFUNDED,
}


def _notify_both(
    db: Session, deal: Deal, payment: EscrowPayment, kind: str, **extra: object
) -> None:
    """Ring both parties' bells about the money.

    Written inline rather than through the outbox, like the rest of the deals
    notifications: a rolled-back mark must not leave a bell claiming money moved.

    `dedup=False` on purpose. The default suppresses an identical UNREAD
    notification, which is right for "you have a new message" and wrong here —
    "your money arrived" and "your money was paid out" are different sentences
    about the same deal, and the second must not be swallowed.
    """
    title_key, body_key = notification_service.keys_for(kind)
    params: dict[str, object] = {
        "number": deal.number,
        "deal_id": deal.id,
        "amount": f"{payment.amount:.2f}",
        "currency": payment.currency,
    }
    params.update(extra)
    for company_id in (deal.buyer_company_id, deal.seller_company_id):
        notification_service.notify_company(
            db,
            company_id,
            kind=kind,
            title_key=title_key,
            body_key=body_key,
            params=params,
            entity="deal",
            entity_id=str(deal.id),
            dedup=False,
        )


def _payload(
    deal: Deal, payment: EscrowPayment, *, extra: dict[str, object] | None = None
) -> dict[str, object]:
    """Event body. Carries both party ids so consumers need no extra query."""
    body: dict[str, object] = {
        "payment_id": payment.id,
        "deal_id": deal.id,
        "deal_number": deal.number,
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "buyer_company_id": deal.buyer_company_id,
        "seller_company_id": deal.seller_company_id,
    }
    body.update(extra or {})
    return body


# ── Provider inbox (the P7 seam) ──────────────────────────────────────────────


def record_provider_event(
    db: Session, provider: str, external_id: str, payload: dict[str, object]
) -> ProviderEvent:
    """Store a raw provider callback, exactly once.

    Idempotency lives in the schema (`UNIQUE (provider, external_id)`); the
    insert runs inside a SAVEPOINT so a retried webhook's IntegrityError cannot
    poison the caller's transaction — it just resolves to the existing row.
    """
    existing = (
        db.query(ProviderEvent)
        .filter(ProviderEvent.provider == provider, ProviderEvent.external_id == external_id)
        .first()
    )
    if existing is not None:
        return existing

    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    event = ProviderEvent(provider=provider, external_id=external_id, payload=payload)
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        # Lost a race with a concurrent delivery of the same callback.
        found = (
            db.query(ProviderEvent)
            .filter(
                ProviderEvent.provider == provider,
                ProviderEvent.external_id == external_id,
            )
            .one()
        )
        return found
    return event


def apply_provider_event(db: Session, event: ProviderEvent) -> dict[str, object]:
    """Turn a provider callback into a `mark`. Skeleton until P7.

    The live rail has no adapter yet, so this records WHY nothing happened and
    stamps the event processed. Leaving it unprocessed instead would grow the
    inbox forever with no trace of the reason.

    P7 replaces the body: parse the payload into an `EscrowStatus`, resolve the
    payment by `provider_ref`, and call `mark`. Note that a provider-driven
    refund needs a staff actor under the current deal rules (`cancelled` is not
    reachable by `system`) — P7 decides whether that is a service account or a
    widening of `deal_service._ACTOR_RULES`. The schema and this seam are ready
    either way.
    """
    if event.processed:
        return {"status": "already_processed", "event_id": event.id}

    event.processed = True
    event.processed_at = utcnow()
    event.error = f"no adapter for provider {event.provider!r} (live escrow lands in P7)"
    db.flush()
    logger.info(
        "escrow_service.provider_event.unsupported",
        extra={"event_id": event.id, "provider": event.provider},
    )
    return {"status": "unsupported", "event_id": event.id}


def now_utc() -> datetime.datetime:
    return utcnow()
