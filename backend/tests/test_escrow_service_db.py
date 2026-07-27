"""Real-Postgres tests for escrow_service (P3 W1 — T1.2 acceptance).

Guarded (localhost test_polymer). Covers what the pure-data matrix cannot: that
the escrow row and the deal it drags move in ONE transaction, that a failed deal
transition takes the escrow mark down with it, that two concurrent marks
serialize on the row lock, and that the provider inbox is idempotent.

The tests are written against a deal walked to the status each case needs, using
the real service both times — a hand-set `deal.status` would prove nothing about
a machine whose whole job is to refuse the moves it is not given.
"""

from __future__ import annotations

import decimal
import threading

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    make_staff,
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
    """A real deal walked negotiation → contract_pending → contract_signed."""
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
    request = make_request(db, company=buyer, account=buyer_acc)

    from app.models.deals import RfqResponse  # noqa: PLC0415

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
    deal_service.transition(
        db, deal, DealStatus.contract_pending, actor_kind=DealActorKind.system
    )
    deal_service.transition(
        db, deal, DealStatus.contract_signed, actor_kind=DealActorKind.system
    )
    return deal, buyer_acc, buyer, seller_acc, seller


def _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller):  # noqa: ANN001
    """paid_escrow → shipped (seller) → delivered (buyer), through the real service."""
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    deal_service.transition_by_party(
        db, deal, seller_acc, DealStatus.shipped, company_id=seller.id
    )
    deal_service.transition_by_party(
        db, deal, buyer_acc, DealStatus.delivered, company_id=buyer.id
    )


# ── open_for_deal ─────────────────────────────────────────────────────────────


@requires_real_db
def test_open_creates_a_pending_payment_and_moves_the_deal(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()

        assert payment.status == EscrowStatus.pending
        assert payment.amount == decimal.Decimal("25000.00")
        assert payment.currency == deal.currency
        assert deal.status == DealStatus.payment_pending, (
            "the deal must follow the invoice in the same transaction"
        )


@requires_real_db
def test_open_is_idempotent(sf) -> None:  # noqa: ANN001
    """Outbox delivery is at-least-once, so this runs twice in the real world."""
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        first = escrow_service.open_for_deal(db, deal)
        db.commit()
        second = escrow_service.open_for_deal(db, deal)
        db.commit()

        assert first.id == second.id
        assert db.query(EscrowPayment).filter(EscrowPayment.deal_id == deal.id).count() == 1


@requires_real_db
def test_open_freezes_the_mode_the_setting_had(sf) -> None:  # noqa: ANN001
    from app.services import escrow_service, settings_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()
        assert payment.mode == "stub"

        # Flipping the rail later must NOT rewrite an existing payment.
        settings_service.set_many(db, {"escrow_mode": "live"}, None)
        db.commit()
        db.refresh(payment)
        assert payment.mode == "stub"


@requires_real_db
def test_open_without_an_amount_leaves_the_deal_alone(sf) -> None:  # noqa: ANN001
    """A deal opened from an inquiry may carry no agreed total. Escrow cannot
    invent one, so the deal waits at contract_signed for staff — it must NOT
    advance to payment_pending with no invoice behind it."""
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db, amount=None)
        db.commit()  # commit the fixture, so the rollback below discards ONLY the attempt

        with pytest.raises(escrow_service.DealAmountMissing):
            escrow_service.open_for_deal(db, deal)
        db.rollback()

        db.refresh(deal)
        assert deal.status == DealStatus.contract_signed
        assert db.query(EscrowPayment).filter(EscrowPayment.deal_id == deal.id).count() == 0


@requires_real_db
def test_open_refuses_a_deal_that_has_not_signed_a_contract(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import deal_service, escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        # Back to negotiation, the way a declined contract leaves it.
        deal.status = DealStatus.negotiation
        db.commit()

        with pytest.raises(deal_service.InvalidDealTransition):
            escrow_service.open_for_deal(db, deal)
        db.rollback()

        db.refresh(deal)
        assert deal.status == DealStatus.negotiation
        assert db.query(EscrowPayment).count() == 0


@requires_real_db
def test_only_one_payment_row_can_exist_per_deal(sf) -> None:  # noqa: ANN001
    """The DB, not just the service, enforces it — every money lookup goes by deal."""
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        escrow_service.open_for_deal(db, deal)
        db.commit()

        db.add(
            EscrowPayment(deal_id=deal.id, amount=decimal.Decimal("1.00"), currency="UZS")
        )
        with pytest.raises(sa.exc.IntegrityError):
            db.flush()
        db.rollback()


# ── mark: funded ──────────────────────────────────────────────────────────────


@requires_real_db
def test_funding_records_who_and_when_and_moves_the_deal(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()

        escrow_service.mark(
            db, payment, EscrowStatus.funded, staff_user=staff, note="MT103 ref 44821"
        )
        db.commit()
        db.refresh(deal)

        assert payment.status == EscrowStatus.funded
        assert payment.funded_at is not None
        assert payment.funded_marked_by == staff.id
        assert payment.note == "MT103 ref 44821"
        assert deal.status == DealStatus.paid_escrow


@requires_real_db
def test_marking_writes_the_event_and_the_audit_entry(sf) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.models.staff import AuditLog  # noqa: PLC0415
    from app.services import escrow_service, event_types  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(
            db, payment, EscrowStatus.funded, staff_user=staff, note="bank statement 12/07"
        )
        db.commit()

        kinds = {e.event_type for e in db.query(DomainEvent).all()}
        assert event_types.ESCROW_OPENED in kinds
        assert event_types.ESCROW_FUNDED in kinds

        audits = [a for a in db.query(AuditLog).all() if a.action == "escrow.mark"]
        assert audits, "a money movement with no audit trail is not acceptable"
        assert audits[0].staff_user_id == staff.id


@requires_real_db
def test_a_note_is_mandatory(sf) -> None:  # noqa: ANN001
    """The note is the operator's link to the bank record. Without it the row is
    an unfalsifiable claim that money moved."""
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()

        for blank in ("", "   "):
            with pytest.raises(escrow_service.NoteRequired):
                escrow_service.mark(
                    db, payment, EscrowStatus.funded, staff_user=staff, note=blank
                )
        db.rollback()
        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_an_invalid_escrow_move_is_refused(sf) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()

        with pytest.raises(escrow_service.InvalidEscrowTransition):
            escrow_service.mark(
                db, payment, EscrowStatus.released, staff_user=staff, note="pay out"
            )
        db.rollback()


@requires_real_db
def test_a_terminal_payment_cannot_be_marked_again(sf) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller)
        escrow_service.mark(db, payment, EscrowStatus.released, staff_user=staff, note="out")
        db.commit()

        for target in (EscrowStatus.funded, EscrowStatus.refunded):
            with pytest.raises(escrow_service.InvalidEscrowTransition):
                escrow_service.mark(db, payment, target, staff_user=staff, note="again")
        db.rollback()


# ── mark: released ────────────────────────────────────────────────────────────


@requires_real_db
def test_release_before_delivery_is_refused(sf) -> None:  # noqa: ANN001
    """Paying the seller out before the buyer confirms delivery is the failure
    this whole feature exists to prevent."""
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        db.commit()

        # paid_escrow — not shipped, not delivered.
        with pytest.raises(escrow_service.EscrowReleaseBeforeDelivery):
            escrow_service.mark(
                db, payment, EscrowStatus.released, staff_user=staff, note="early payout"
            )
        db.rollback()
        db.refresh(payment)
        db.refresh(deal)
        assert payment.status == EscrowStatus.funded
        assert payment.released_at is None
        assert deal.status == DealStatus.paid_escrow

        # Ship it: still not delivered, still refused.
        from app.services import deal_service  # noqa: PLC0415

        deal_service.transition_by_party(
            db, deal, seller_acc, DealStatus.shipped, company_id=seller.id
        )
        db.commit()
        with pytest.raises(escrow_service.EscrowReleaseBeforeDelivery):
            escrow_service.mark(
                db, payment, EscrowStatus.released, staff_user=staff, note="early payout"
            )
        db.rollback()
        assert buyer_acc and buyer  # both parties exist; the guard is about status


@requires_real_db
def test_release_after_delivery_completes_the_deal(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        _walk_to_delivered(db, deal, buyer_acc, seller_acc, buyer, seller)
        db.commit()

        escrow_service.mark(
            db, payment, EscrowStatus.released, staff_user=staff, note="paid out 14/07"
        )
        db.commit()
        db.refresh(deal)

        assert payment.status == EscrowStatus.released
        assert payment.released_at is not None
        assert payment.released_marked_by == staff.id
        assert deal.status == DealStatus.completed


# ── mark: refunded ────────────────────────────────────────────────────────────


@requires_real_db
def test_refund_before_funding_cancels_the_deal(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()

        escrow_service.mark(
            db, payment, EscrowStatus.refunded, staff_user=staff, note="buyer withdrew"
        )
        db.commit()
        db.refresh(deal)

        assert payment.status == EscrowStatus.refunded
        assert payment.refunded_marked_by == staff.id
        assert deal.status == DealStatus.cancelled
        assert deal.cancelled_reason is not None
        assert "escrow_refund" in deal.cancelled_reason


@requires_real_db
def test_refunding_funded_money_requires_a_dispute_first(sf) -> None:  # noqa: ANN001
    """FR-D8 in the money path. Once the money is in escrow the deal cannot just
    be cancelled — staff must dispute it, which makes the refund a recorded
    decision. The refused mark must leave the payment untouched."""
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import deal_service, escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, _seller_acc, _seller = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        db.commit()

        with pytest.raises(deal_service.InvalidDealTransition):
            escrow_service.mark(
                db, payment, EscrowStatus.refunded, staff_user=staff, note="give it back"
            )
        db.rollback()
        db.refresh(payment)
        assert payment.status == EscrowStatus.funded, (
            "a failed deal transition must take the escrow mark down with it"
        )
        assert payment.refunded_at is None

        # With a dispute open, the same refund goes through.
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.disputed, reason="never shipped",
            company_id=buyer.id,
        )
        db.commit()
        escrow_service.mark(
            db, payment, EscrowStatus.refunded, staff_user=staff, note="returned 15/07"
        )
        db.commit()
        db.refresh(deal)
        assert payment.status == EscrowStatus.refunded
        assert deal.status == DealStatus.cancelled


# ── concurrency ───────────────────────────────────────────────────────────────


@requires_real_db
def test_two_simultaneous_funding_marks_apply_once(sf, engine) -> None:  # noqa: ANN001
    """Two operators clicking "funded" at the same moment. The row lock must make
    the second one see `funded` and refuse, or the deal would be transitioned
    twice and the timeline would show a move that never happened."""
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_at_contract_signed(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        db.commit()
        payment_id, staff_id, deal_id = payment.id, staff.id, deal.id

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt() -> None:
        from app.models.staff import StaffUser  # noqa: PLC0415

        with session_factory(engine)() as db:
            row = db.get(EscrowPayment, payment_id)
            user = db.get(StaffUser, staff_id)
            barrier.wait(timeout=10)
            try:
                escrow_service.mark(
                    db, row, EscrowStatus.funded, staff_user=user, note="race"
                )
                db.commit()
                outcomes.append("ok")
            except Exception as exc:  # noqa: BLE001 — the losing thread's verdict
                db.rollback()
                outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert outcomes.count("ok") == 1, f"exactly one mark must win, got {outcomes}"

    with sf() as db:
        from app.models.deals import Deal, DealStatusHistory  # noqa: PLC0415

        assert db.get(EscrowPayment, payment_id).status == EscrowStatus.funded
        assert db.get(Deal, deal_id).status == DealStatus.paid_escrow
        moves = (
            db.query(DealStatusHistory)
            .filter(
                DealStatusHistory.deal_id == deal_id,
                DealStatusHistory.to_status == DealStatus.paid_escrow,
            )
            .count()
        )
        assert moves == 1, "the timeline must not show the same move twice"


# ── provider inbox (the P7 seam) ──────────────────────────────────────────────


@requires_real_db
def test_a_retried_provider_callback_is_recorded_once(sf) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        first = escrow_service.record_provider_event(
            db, "bank", "op-4821", {"status": "funded", "amount": "25000.00"}
        )
        db.commit()
        second = escrow_service.record_provider_event(
            db, "bank", "op-4821", {"status": "funded", "amount": "25000.00"}
        )
        db.commit()

        assert first.id == second.id, "a retried webhook must resolve to the same row"
        assert db.query(ProviderEvent).count() == 1


@requires_real_db
def test_a_different_operation_id_is_a_different_row(sf) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        escrow_service.record_provider_event(db, "bank", "op-1", {})
        escrow_service.record_provider_event(db, "bank", "op-2", {})
        escrow_service.record_provider_event(db, "other-bank", "op-1", {})
        db.commit()
        assert db.query(ProviderEvent).count() == 3


@requires_real_db
def test_applying_a_provider_event_is_a_recorded_no_op_until_p7(sf) -> None:  # noqa: ANN001
    """The live rail has no adapter yet. Applying an event must mark it processed
    with the reason recorded — silently leaving it unprocessed would have the
    inbox grow forever with no trace of why."""
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        event = escrow_service.record_provider_event(db, "bank", "op-9", {"status": "funded"})
        result = escrow_service.apply_provider_event(db, event)
        db.commit()

        assert event.processed is True
        assert event.processed_at is not None
        assert event.error
        assert result["status"] == "unsupported"

        # Idempotent: a second apply changes nothing.
        stamped = event.processed_at
        again = escrow_service.apply_provider_event(db, event)
        db.commit()
        assert again["status"] == "already_processed"
        assert event.processed_at == stamped
