"""Escrow payment service (R4 / P3 — T1.2; R6 / P7.b). The money side of a deal.

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

**P7.b — the provider rail.** A bank reports movements through
`apply_provider_event`, which either applies them via `mark_from_provider` or
HOLDS them for an operator. The two doors (`mark` for an operator,
`mark_from_provider` for a bank) share one body, `_apply_mark`: they differ only
in who is accountable, and every guard above applies to both. A rail that had
its own, looser rules would be the way around the guards, not a second way in.
"""

from __future__ import annotations

import datetime
import decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.integrations.escrow import events as provider_events_map
from app.models.deals import Deal
from app.models.enums import DealActorKind, DealStatus, EscrowStatus
from app.models.payments import ESCROW_MODE_LIVE, ESCROW_MODE_STUB, EscrowPayment, ProviderEvent
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


# ── The provider rail: what a bank may decide on its own (P7.b) ───────────────

#: Statuses a provider callback may apply UNATTENDED.
#:
#: `funded` and `released` only move a deal forward, and their deal-side targets
#: (`paid_escrow`, `completed`) are already `system`-only — a bank reporting them
#: is reporting a fact. `refunded` is absent on purpose: it CANCELS the deal, and
#: `cancelled` is deliberately unreachable by `system` (`deal_service._ACTOR_RULES`).
#:
#: That gap is the open question P3 recorded in this module. The answer is
#: neither a service account nor a widening of the actor rules: a refund is held
#: for an operator, because ending a deal is a decision that needs a person and a
#: reason on it. FR-D8 already says the same thing on the operator path — out of
#: funded escrow, a refund requires the deal disputed first.
AUTO_APPLIED: frozenset[EscrowStatus] = frozenset({EscrowStatus.funded, EscrowStatus.released})

#: Prefix stamped into `provider_events.error` when an event was understood but
#: deliberately not applied. The operator queue is a scan for it; a held event is
#: `processed` because we DID decide what it means — the decision was "a human".
HOLD_PREFIX = "hold:"

HOLD_UNKNOWN_PROVIDER = "unknown_provider"
HOLD_MALFORMED = "malformed"
HOLD_UNKNOWN_REF = "unknown_ref"
HOLD_WRONG_RAIL = "wrong_rail"
HOLD_AMOUNT_MISMATCH = "amount_mismatch"
HOLD_CURRENCY_MISMATCH = "currency_mismatch"
HOLD_NEEDS_OPERATOR = "needs_operator"
HOLD_RELEASE_BEFORE_DELIVERY = "release_before_delivery"
HOLD_INVALID_TRANSITION = "invalid_transition"
HOLD_DEAL_BLOCKED = "deal_blocked"


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


class WrongRail(Exception):
    """A provider tried to move a payment opened on the stub rail (or vice versa).

    `escrow_payments.mode` is frozen at creation, so flipping the runtime setting
    can never rewrite how a payment already in flight may be marked.
    """


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
    return _apply_mark(db, payment, to_status, note=clean_note, staff_user=staff_user, event=None)


def mark_from_provider(
    db: Session,
    payment: EscrowPayment,
    to_status: EscrowStatus,
    event: ProviderEvent,
) -> EscrowPayment:
    """Record a movement the PROVIDER reported. No staff member, by design.

    The callback is the evidence, which is why `escrow_payments.*_marked_by` has
    been nullable since P3 — nothing in the schema changes to support a bank.
    The note points back at the inbox row so the payment and the raw callback are
    joinable by eye.

    Only usable on a payment opened on the live rail (`WrongRail` otherwise): a
    payment whose movement an operator is reconciling by hand must not also be
    moved by a provider behind their back.
    """
    if payment.mode != ESCROW_MODE_LIVE:
        raise WrongRail(f"payment {payment.id} is on the {payment.mode} rail")
    note = f"provider:{event.provider}:{event.external_id}"
    return _apply_mark(db, payment, to_status, note=note, staff_user=None, event=event)


def _apply_mark(
    db: Session,
    payment: EscrowPayment,
    to_status: EscrowStatus,
    *,
    note: str,
    staff_user: StaffUser | None,
    event: ProviderEvent | None,
) -> EscrowPayment:
    """Shared body of `mark` (operator) and `mark_from_provider` (bank).

    The two doors differ ONLY in who is accountable; every rule below — the row
    lock, the transition table, the release-before-delivery guard, the deal being
    dragged in the same transaction — applies identically to both. Splitting the
    rules per door is how a rail quietly becomes the way around a guard.
    """
    clean_note = note
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
    # NULL on the provider path — the inbox row is the evidence there, and an
    # invented staff id would make a bank-driven mark indistinguishable from an
    # operator's assertion.
    setattr(locked, f"{stamp}_marked_by", staff_user.id if staff_user is not None else None)
    locked.note = clean_note
    db.flush()

    _drag_the_deal(db, deal, to_status, staff_user, clean_note)

    extra: dict[str, object] = {"from": frm.value, "note": clean_note}
    if event is not None:
        extra["provider"] = event.provider
        extra["provider_event_id"] = event.id
    event_service.emit(
        db,
        _EVENT_FOR[to_status],
        "escrow_payment",
        locked.id,
        _payload(deal, locked, extra=extra),
    )
    audit_service.write_audit(
        db,
        staff_user.id if staff_user is not None else None,
        "escrow.mark" if event is None else "escrow.mark_provider",
        "escrow_payments",
        str(locked.id),
        {
            "deal_id": deal.id,
            "from": frm.value,
            "to": to_status.value,
            "note": clean_note,
            **({"provider_event_id": event.id} if event is not None else {}),
        },
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
    staff_user: StaffUser | None,
    note: str,
) -> None:
    """Apply the deal transition this escrow move asserts.

    `funded`/`released` are consequences of an event, so they go in as `system`.
    A refund CANCELS the deal, and a cancel is a decision with a reason — it is
    attributed to the staff member who marked it, and carries the `escrow_refund`
    marker so a money-driven cancellation is distinguishable from a party simply
    walking away.

    Which is why a refund with no staff member behind it is refused here rather
    than handed to `deal_service` as `system`: `apply_provider_event` already
    holds provider refunds for an operator, and this is the second lock on the
    same door.
    """
    target = _DEAL_EFFECT[to_status]
    if to_status is EscrowStatus.refunded:
        if staff_user is None:
            raise StaffRequired(f"deal {deal.id}: a refund needs a staff actor")
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


def _hold(
    db: Session, event: ProviderEvent, reason: str, detail: str = ""
) -> dict[str, object]:
    """Stamp an event as understood-but-not-applied, and say why.

    `processed` is True because we DID decide what the callback means — the
    decision was "a human has to look at this". Leaving it unprocessed would have
    the sweeper retry a verdict that will never change, and the inbox would grow
    with no trace of the reason.
    """
    event.processed = True
    event.processed_at = utcnow()
    event.error = f"{HOLD_PREFIX}{reason}" + (f": {detail}" if detail else "")
    db.flush()
    logger.warning(
        "escrow_service.provider_event.held",
        extra={"event_id": event.id, "provider": event.provider, "reason": reason},
    )
    return {"status": "held", "event_id": event.id, "reason": reason, "detail": detail}


def _by_provider_ref(db: Session, provider_ref: str) -> EscrowPayment | None:
    return (
        db.query(EscrowPayment).filter(EscrowPayment.provider_ref == provider_ref).one_or_none()
    )


def apply_provider_event(db: Session, event: ProviderEvent) -> dict[str, object]:
    """Turn a provider callback into a `mark` — or hold it for an operator.

    The rail is deliberately one-directional. A provider may report the two
    movements that only carry a deal FORWARD (`funded`, `released`, see
    `AUTO_APPLIED`); everything else is recorded, explained and left to a human.
    In particular a refund is never applied unattended — that is the answer to
    the question P3 left in this module, and it needed no service account and no
    change to `deal_service._ACTOR_RULES`.

    Every refusal is a hold with a named reason rather than an exception,
    because the caller is a batch task: one poisoned transaction would take the
    rest of the batch down with it. The mark itself runs inside a SAVEPOINT for
    the same reason — a refused deal transition rolls back to the savepoint and
    the hold is still written.
    """
    if event.processed:
        return {"status": "already_processed", "event_id": event.id}

    try:
        normalized = provider_events_map.normalize(event.provider, event.payload)
    except provider_events_map.UnknownProvider:
        return _hold(db, event, HOLD_UNKNOWN_PROVIDER, event.provider)
    except provider_events_map.MalformedEvent as exc:
        return _hold(db, event, HOLD_MALFORMED, str(exc))

    payment = _by_provider_ref(db, normalized.provider_ref)
    if payment is None:
        return _hold(db, event, HOLD_UNKNOWN_REF, normalized.provider_ref)
    if payment.mode != ESCROW_MODE_LIVE:
        return _hold(db, event, HOLD_WRONG_RAIL, f"payment {payment.id} is {payment.mode}")

    to_status = EscrowStatus(normalized.status)

    # An acknowledgement that the escrow exists. Not a movement, nothing to do —
    # but it IS decided, so it does not come back through the sweeper.
    if to_status is EscrowStatus.pending or to_status is payment.status:
        event.processed = True
        event.processed_at = utcnow()
        db.flush()
        return {"status": "noop", "event_id": event.id, "payment_id": payment.id}

    # Money that does not match the invoice. Partial payment is a real banking
    # behaviour we do not model; accepting it as `funded` would tell the seller
    # they have been paid in full.
    if normalized.amount is not None and normalized.amount != payment.amount:
        return _hold(
            db, event, HOLD_AMOUNT_MISMATCH, f"{normalized.amount} vs {payment.amount}"
        )
    if normalized.currency is not None and normalized.currency != payment.currency:
        return _hold(
            db, event, HOLD_CURRENCY_MISMATCH, f"{normalized.currency} vs {payment.currency}"
        )

    if to_status not in AUTO_APPLIED:
        return _hold(db, event, HOLD_NEEDS_OPERATOR, to_status.value)

    try:
        with db.begin_nested():
            mark_from_provider(db, payment, to_status, event)
    except EscrowReleaseBeforeDelivery as exc:
        return _hold(db, event, HOLD_RELEASE_BEFORE_DELIVERY, str(exc))
    except InvalidEscrowTransition as exc:
        return _hold(db, event, HOLD_INVALID_TRANSITION, str(exc))
    except WrongRail as exc:  # pragma: no cover — guarded above; kept as a second lock
        return _hold(db, event, HOLD_WRONG_RAIL, str(exc))
    except (deal_service.InvalidDealTransition, deal_service.ActorNotAllowed) as exc:
        return _hold(db, event, HOLD_DEAL_BLOCKED, str(exc))

    event.processed = True
    event.processed_at = utcnow()
    event.error = None
    db.flush()
    logger.info(
        "escrow_service.provider_event.applied",
        extra={"event_id": event.id, "payment_id": payment.id, "to": to_status.value},
    )
    return {
        "status": "applied",
        "event_id": event.id,
        "payment_id": payment.id,
        "to": to_status.value,
    }


def reconcile_with_provider(
    db: Session,
    client: object,
    *,
    provider: str = provider_events_map.PROVIDER_GENERIC,
    limit: int = 100,
) -> dict[str, object]:
    """Ask the provider where each live, non-terminal payment stands.

    The bank's notification format is unknown and Didox has no partner webhooks,
    so polling is not a fallback — it is the mechanism we can rely on.

    A polled status becomes a **synthesized callback row** and goes through
    `apply_provider_event` like any pushed one. One path from "the provider says
    X" to "we did Y": a second, parallel path is where a guard eventually gets
    forgotten. It also makes the poll idempotent for free — the synthetic
    `external_id` is deterministic per (reference, status), so an unresolved
    disagreement is reported ONCE rather than on every sweep, and then lives in
    `held_provider_events` until an operator settles it.

    Never raises. A dead provider stops the sweep (`unavailable=True`) and
    touches nothing: provider unavailability degrades, it never moves or blocks a
    deal.
    """
    from app.integrations.escrow.client import ProviderUnavailable  # noqa: PLC0415

    counts: dict[str, int] = {
        "checked": 0,
        "agreed": 0,
        "applied": 0,
        "held": 0,
        "already_processed": 0,
        "noop": 0,
        "unknown": 0,
        "unmodelled": 0,
    }
    reasons: list[str] = []
    held_ids: list[int] = []
    unavailable = False

    candidates = (
        db.query(EscrowPayment)
        .filter(
            EscrowPayment.mode == ESCROW_MODE_LIVE,
            EscrowPayment.provider_ref.isnot(None),
            EscrowPayment.status.in_([EscrowStatus.pending, EscrowStatus.funded]),
        )
        .order_by(EscrowPayment.id)
        .limit(limit)
        .all()
    )

    for payment in candidates:
        ref = payment.provider_ref
        if ref is None:  # pragma: no cover — filtered above
            continue
        counts["checked"] += 1
        try:
            raw = client.get_status(ref)  # type: ignore[attr-defined]
        except ProviderUnavailable as exc:
            unavailable = True
            logger.warning("escrow_service.reconcile.unavailable", extra={"error": str(exc)})
            break

        if not isinstance(raw, str) or not raw.strip():
            counts["unknown"] += 1
            continue
        status_value = raw.strip().lower()
        if status_value not in provider_events_map.KNOWN_STATUSES:
            # A status we do not model. Counted and logged, never guessed at.
            counts["unmodelled"] += 1
            logger.warning(
                "escrow_service.reconcile.unmodelled_status",
                extra={"payment_id": payment.id, "provider_status": raw},
            )
            continue
        if status_value == payment.status.value:
            counts["agreed"] += 1
            continue

        synthetic_id = f"poll:{ref}:{status_value}"
        event = record_provider_event(
            db,
            provider,
            synthetic_id,
            {
                "event_id": synthetic_id,
                "escrow_ref": ref,
                "status": status_value,
                "_source": "reconcile",
            },
        )
        outcome = apply_provider_event(db, event)
        key = str(outcome.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
        if key == "held":
            reasons.append(str(outcome.get("reason", "")))
            held_ids.append(payment.id)

    report: dict[str, object] = dict(counts)
    report["unavailable"] = unavailable
    report["reasons"] = reasons
    report["held_payment_ids"] = held_ids
    return report


def held_provider_events(db: Session, limit: int = 100) -> list[dict[str, object]]:
    """The operator queue: callbacks we understood and deliberately did not apply.

    Self-clearing, and that is why a held event needs neither a resolve button
    nor an extra column: a hold is a DISAGREEMENT between what the bank claims
    and what we record, so once the operator marks the payment by hand the two
    agree and the row stops matching. An event we could not read at all has no
    claim to compare, so it stays listed until someone deals with it.
    """
    rows = (
        db.query(ProviderEvent)
        .filter(ProviderEvent.error.like(f"{HOLD_PREFIX}%"))
        .order_by(ProviderEvent.id.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, object]] = []
    for event in rows:
        reason = (event.error or "")[len(HOLD_PREFIX) :].split(":", 1)[0]
        item: dict[str, object] = {
            "event_id": event.id,
            "provider": event.provider,
            "external_id": event.external_id,
            "reason": reason,
            "detail": event.error or "",
            "created_at": event.created_at,
            "claimed_status": None,
            "payment_id": None,
            "payment_status": None,
            "deal_id": None,
        }
        try:
            normalized = provider_events_map.normalize(event.provider, event.payload)
        except (provider_events_map.UnknownProvider, provider_events_map.MalformedEvent):
            out.append(item)  # unreadable → no claim to reconcile against
            continue

        payment = _by_provider_ref(db, normalized.provider_ref)
        item["claimed_status"] = normalized.status
        if payment is None:
            out.append(item)
            continue
        if payment.status.value == normalized.status:
            continue  # the operator resolved it; bank and ledger agree again
        item["payment_id"] = payment.id
        item["payment_status"] = payment.status.value
        item["deal_id"] = payment.deal_id
        out.append(item)
    return out


def now_utc() -> datetime.datetime:
    return utcnow()
