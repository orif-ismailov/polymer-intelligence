"""Real-Postgres tests for the escrow provider-event rail (R6 / P7.b — T1.2–T1.4).

This is the inbound half of the live escrow: a bank says money moved, and we
decide what that means. The rules being pinned here are the ones that decide
whether an unattended integration is safe to switch on:

  * a provider may only move a payment FORWARD by itself. `funded` and
    `released` are consequences; `refunded` kills the deal, and killing a deal
    is a decision with a person and a reason attached (FR-D8). So a refund
    callback is recorded and HELD, never applied — this is the answer to the
    question P3 left in `apply_provider_event`'s docstring, and it needed
    neither a service account nor a widening of `deal_service._ACTOR_RULES`;
  * `release before delivery` holds on the provider path exactly as it refuses
    on the operator path. A bank paying out early is the failure escrow exists
    to prevent, and the rail must not become the way around it;
  * a payment opened on the STUB rail can never be moved by a provider. `mode`
    is frozen per row precisely so flipping the runtime setting cannot rewrite
    the rules for payments already in flight;
  * an amount that disagrees with the invoice holds. Partial payment is a real
    banking behaviour we do not model, and silently accepting it as `funded`
    would tell a seller they have been paid in full.

Guarded (localhost `test_polymer`), like the rest of the escrow DB suite.
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    migrate_head,
    requires_real_db,
    session_factory,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


# ── fixtures ──────────────────────────────────────────────────────────────────


def _verified(db, tax, phone):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _deal_at_contract_signed(db, *, amount=decimal.Decimal("25000.00")):  # noqa: ANN001, ANN202
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
    request = make_request(db, company=buyer, account=buyer_acc)

    response = RfqResponse(
        request_id=request.id,
        company_id=seller.id,
        created_by_user_account_id=seller_acc.id,
        price=decimal.Decimal("1250.00"),
        currency="USD",
        qty=decimal.Decimal("20"),
        qty_unit="MT",
    )
    db.add(response)
    db.flush()

    deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
    deal.amount = amount
    db.flush()
    deal_service.transition(db, deal, DealStatus.contract_pending, actor_kind=DealActorKind.system)
    deal_service.transition(db, deal, DealStatus.contract_signed, actor_kind=DealActorKind.system)
    return deal, buyer_acc, buyer, seller_acc, seller


def _live_payment(db, *, amount=decimal.Decimal("25000.00"), ref="ESC-1"):  # noqa: ANN001, ANN202
    """A deal with escrow opened on the LIVE rail and a bank reference on it."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    deal, buyer_acc, buyer, seller_acc, seller = _deal_at_contract_signed(db, amount=amount)
    payment = escrow_service.open_for_deal(db, deal, mode="live")
    payment.provider_ref = ref
    db.flush()
    return payment, deal, buyer_acc, buyer, seller_acc, seller


def _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller):  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    deal_service.transition_by_party(db, deal, seller_acc, DealStatus.shipped, company_id=seller.id)
    deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.delivered, company_id=buyer.id)


def _event(db, payload, *, provider="generic", external_id="bank-op-1"):  # noqa: ANN001, ANN202
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    return escrow_service.record_provider_event(db, provider, external_id, payload)


def _payload(status, *, ref="ESC-1", event_id="bank-op-1", **extra):  # noqa: ANN001, ANN202
    body = {"event_id": event_id, "escrow_ref": ref, "status": status}
    body.update(extra)
    return body


def _held(event) -> bool:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    return bool(event.error and event.error.startswith(escrow_service.HOLD_PREFIX))


# ── mark_from_provider ────────────────────────────────────────────────────────


@requires_real_db
def test_provider_mark_records_the_event_instead_of_a_staff_id(sf) -> None:  # noqa: ANN001
    """`funded_marked_by` stays NULL on the live rail — the callback is the evidence.

    The column has been nullable since P3 for exactly this; nothing about the
    schema changes to support a bank.
    """
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _live_payment(db)
        event = _event(db, _payload("funded"))
        db.commit()

        escrow_service.mark_from_provider(db, payment, EscrowStatus.funded, event)
        db.commit()

        db.refresh(payment)
        db.refresh(deal)
        assert payment.status == EscrowStatus.funded
        assert payment.funded_marked_by is None
        assert payment.funded_at is not None
        assert "bank-op-1" in (payment.note or ""), "the note must point at the callback"
        assert deal.status == DealStatus.paid_escrow


@requires_real_db
def test_provider_mark_refuses_a_payment_opened_on_the_stub_rail(sf) -> None:  # noqa: ANN001
    """A rail flip must never rewrite the rules for payments already in flight."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        payment = escrow_service.open_for_deal(db, deal, mode="stub")
        event = _event(db, _payload("funded"))
        db.commit()

        with pytest.raises(escrow_service.WrongRail):
            escrow_service.mark_from_provider(db, payment, EscrowStatus.funded, event)
        db.rollback()

        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_operator_mark_still_requires_a_staff_member_and_a_note(sf) -> None:  # noqa: ANN001
    """The P3 contract is untouched by the provider path being added next to it."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db)
        db.commit()

        with pytest.raises(escrow_service.StaffRequired):
            escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=None, note="x")
        db.rollback()


# ── apply_provider_event: the happy path ──────────────────────────────────────


@requires_real_db
def test_a_funded_callback_moves_the_payment_and_the_deal(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _live_payment(db)
        event = _event(db, _payload("funded", amount="25000.00", currency="USD"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["status"] == "applied"
        db.refresh(payment)
        db.refresh(deal)
        db.refresh(event)
        assert payment.status == EscrowStatus.funded
        assert deal.status == DealStatus.paid_escrow
        assert event.processed is True
        assert event.error is None


@requires_real_db
def test_a_released_callback_after_delivery_completes_the_deal(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, deal, buyer_acc, buyer, seller_acc, seller = _live_payment(db)
        funded = _event(db, _payload("funded"))
        escrow_service.apply_provider_event(db, funded)
        _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller)
        db.commit()

        released = _event(db, _payload("released", event_id="bank-op-2"), external_id="bank-op-2")
        db.commit()
        result = escrow_service.apply_provider_event(db, released)
        db.commit()

        assert result["status"] == "applied"
        db.refresh(payment)
        db.refresh(deal)
        assert payment.status == EscrowStatus.released
        assert deal.status == DealStatus.completed


@requires_real_db
def test_replaying_the_same_callback_changes_nothing(sf) -> None:  # noqa: ANN001
    """At-least-once delivery is the norm; the second apply must be inert."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals.payment_models import ProviderEvent  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _live_payment(db)
        first = _event(db, _payload("funded"))
        db.commit()
        escrow_service.apply_provider_event(db, first)
        db.commit()

        # Same provider + external_id → the inbox collapses it onto the same row.
        again = _event(db, _payload("funded"))
        db.commit()
        result = escrow_service.apply_provider_event(db, again)
        db.commit()

        assert again.id == first.id
        assert result["status"] == "already_processed"
        assert db.query(ProviderEvent).count() == 1
        db.refresh(payment)
        assert payment.funded_at is not None


@requires_real_db
def test_a_second_distinct_callback_for_a_status_already_reached_is_a_noop(sf) -> None:  # noqa: ANN001
    """A bank re-sending `funded` under a NEW event id must not double-apply."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db)
        escrow_service.apply_provider_event(db, _event(db, _payload("funded")))
        db.commit()

        duplicate = _event(
            db, _payload("funded", event_id="bank-op-9"), external_id="bank-op-9"
        )
        db.commit()
        result = escrow_service.apply_provider_event(db, duplicate)
        db.commit()

        assert result["status"] == "noop"
        db.refresh(payment)
        assert payment.status == EscrowStatus.funded


# ── apply_provider_event: the holds ───────────────────────────────────────────


@requires_real_db
def test_a_refund_callback_is_held_for_an_operator(sf) -> None:  # noqa: ANN001
    """The answer to P3's open question: a refund is never applied unattended.

    `cancelled` is not reachable by `system` and we do NOT widen that rule —
    ending a deal is a decision, and the callback becomes an operator queue item
    rather than a silent reversal.
    """
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _live_payment(db)
        escrow_service.apply_provider_event(db, _event(db, _payload("funded")))
        db.commit()

        event = _event(db, _payload("refunded", event_id="bank-op-3"), external_id="bank-op-3")
        db.commit()
        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["status"] == "held"
        assert result["reason"] == escrow_service.HOLD_NEEDS_OPERATOR
        db.refresh(payment)
        db.refresh(deal)
        db.refresh(event)
        assert payment.status == EscrowStatus.funded, "the refund must not have been applied"
        assert deal.status == DealStatus.paid_escrow
        assert event.processed is True, "a held event is decided, not pending"
        assert _held(event)


@requires_real_db
def test_a_release_before_delivery_is_held_not_applied(sf) -> None:  # noqa: ANN001
    """The bank paying out early must not become the way around the guard."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _live_payment(db)
        escrow_service.apply_provider_event(db, _event(db, _payload("funded")))
        db.commit()

        event = _event(db, _payload("released", event_id="bank-op-4"), external_id="bank-op-4")
        db.commit()
        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_RELEASE_BEFORE_DELIVERY
        db.refresh(payment)
        assert payment.status == EscrowStatus.funded


@requires_real_db
def test_an_amount_that_disagrees_with_the_invoice_is_held(sf) -> None:  # noqa: ANN001
    """Partial payment is real and unmodelled — it must not read as paid in full."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db, amount=decimal.Decimal("25000.00"))
        event = _event(db, _payload("funded", amount="10000.00"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_AMOUNT_MISMATCH
        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_a_matching_amount_written_differently_still_applies(sf) -> None:  # noqa: ANN001
    """25000 and 25000.00 are the same money; only a real difference holds."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db, amount=decimal.Decimal("25000.00"))
        event = _event(db, _payload("funded", amount="25000"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["status"] == "applied"
        db.refresh(payment)
        assert payment.status == EscrowStatus.funded


@requires_real_db
def test_a_currency_that_disagrees_is_held(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    with sf() as db:
        _live_payment(db)  # deal currency is USD
        event = _event(db, _payload("funded", currency="UZS"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_CURRENCY_MISMATCH


@requires_real_db
def test_an_unknown_escrow_reference_is_held(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    with sf() as db:
        _live_payment(db, ref="ESC-1")
        event = _event(db, _payload("funded", ref="ESC-NOBODY"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_UNKNOWN_REF
        db.refresh(event)
        assert event.processed is True


@requires_real_db
def test_a_callback_for_a_stub_payment_is_held(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        payment = escrow_service.open_for_deal(db, deal, mode="stub")
        payment.provider_ref = "ESC-1"
        event = _event(db, _payload("funded"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_WRONG_RAIL
        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_an_unmodelled_status_is_held_with_a_readable_reason(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    with sf() as db:
        _live_payment(db)
        event = _event(db, _payload("partially_funded"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_MALFORMED
        db.refresh(event)
        assert "partially_funded" in (event.error or "")


@requires_real_db
def test_a_provider_with_no_mapper_is_held(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    with sf() as db:
        _live_payment(db)
        event = _event(db, _payload("funded"), provider="kapitalbank")
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["reason"] == escrow_service.HOLD_UNKNOWN_PROVIDER


@requires_real_db
def test_a_pending_acknowledgement_is_processed_and_does_nothing(sf) -> None:  # noqa: ANN001
    """Banks ack the registration of an escrow; that is not a money movement."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db)
        event = _event(db, _payload("pending"))
        db.commit()

        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert result["status"] == "noop"
        db.refresh(payment)
        db.refresh(event)
        assert payment.status == EscrowStatus.pending
        assert event.processed is True
        assert not _held(event)


@requires_real_db
def test_a_hold_leaves_the_outer_transaction_usable(sf) -> None:  # noqa: ANN001
    """A refused mark rolls back to a savepoint, not over the caller's work.

    The task applies a batch of events in one session; one poisoned transaction
    would take the whole batch down with it.
    """
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import EscrowStatus  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _live_payment(db)
        bad = _event(db, _payload("released"))  # release before delivery → held
        db.commit()

        escrow_service.apply_provider_event(db, bad)
        good = _event(db, _payload("funded", event_id="bank-op-5"), external_id="bank-op-5")
        escrow_service.apply_provider_event(db, good)
        db.commit()

        db.refresh(payment)
        assert payment.status == EscrowStatus.funded, (
            "the held event must not have poisoned the session"
        )


# ── the operator queue ────────────────────────────────────────────────────────


@requires_real_db
def test_held_events_list_only_while_the_disagreement_stands(sf) -> None:  # noqa: ANN001
    """The queue self-clears: once the operator marks the payment by hand, the
    bank and we agree again and the row drops out. That is why a held event
    needs no resolve button and no extra column."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from tests._verification_db import make_staff  # noqa: PLC0415

    with sf() as db:
        payment, deal, buyer_acc, buyer, seller_acc, seller = _live_payment(db)
        escrow_service.apply_provider_event(db, _event(db, _payload("funded")))
        _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller)
        db.commit()

        # The bank says refunded; we hold it.
        event = _event(db, _payload("refunded", event_id="bank-op-6"), external_id="bank-op-6")
        db.commit()
        escrow_service.apply_provider_event(db, event)
        db.commit()

        held = escrow_service.held_provider_events(db)
        assert [h["event_id"] for h in held] == [event.id]
        assert held[0]["claimed_status"] == "refunded"
        assert held[0]["payment_status"] == EscrowStatus.funded.value

        # The operator disputes the deal and marks the refund by hand.
        staff = make_staff(db)
        deal_service.transition(
            db, deal, DealStatus.disputed, actor_kind=deal_service.DealActorKind.staff,
            actor_id=staff.id, reason="bank refunded",
        )
        escrow_service.mark(
            db, payment, EscrowStatus.refunded, staff_user=staff, note="bank statement 42"
        )
        db.commit()

        assert escrow_service.held_provider_events(db) == []
