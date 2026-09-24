"""Real-Postgres tests for the DIRECT payment rail (`escrow_mode=direct`).

There is no bank yet, so the buyer pays the seller by transfer on the contract's
details and nobody holds the money in between. The deal still needs to know
whether it was paid, and the only party that can see the money arrive is the
seller — so on this rail the seller confirms receipt, and nothing else changes:

  * prepayment — confirm → paid_escrow → shipped → delivered → completed;
  * postpayment — the seller may ship straight from payment_pending, and the
    deal completes the moment BOTH «Получено» and «Оплата получена» exist,
    in whichever order they happen.

The stub and live rails keep their rules: a party can move neither their money
nor a payment_pending deal into shipped.
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


def _verified(db, tax, phone):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _awaiting_payment(db, *, mode="direct"):  # noqa: ANN001, ANN202
    """A real deal walked to payment_pending, its payment opened on `mode`.

    Named explicitly: the suite's conftest pins `ESCROW_MODE=stub`, and the
    shipped default (`direct`) is asserted in `test_escrow_client`."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
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
    deal.amount = decimal.Decimal("25000.00")
    db.flush()
    for status_ in (DealStatus.contract_pending, DealStatus.contract_signed):
        deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
    payment = escrow_service.open_for_deal(db, deal, mode=mode)
    return deal, payment, buyer_acc, buyer, seller_acc, seller


def _ship(db, deal, seller_acc, seller):  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    deal_service.transition_by_party(db, deal, seller_acc, DealStatus.shipped, company_id=seller.id)


def _receive(db, deal, buyer_acc, buyer):  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.delivered, company_id=buyer.id)


@requires_real_db
def test_prepayment_the_seller_confirms_then_ships_and_the_deal_completes(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, payment, buyer_acc, buyer, seller_acc, seller = _awaiting_payment(db)

        escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        assert payment.status == EscrowStatus.funded
        assert payment.funded_at is not None
        assert deal.status == DealStatus.paid_escrow

        _ship(db, deal, seller_acc, seller)
        _receive(db, deal, buyer_acc, buyer)
        db.commit()

        db.refresh(payment)
        assert deal.status == DealStatus.completed, "paid and received — nothing is left to wait for"
        assert payment.status == EscrowStatus.released


@requires_real_db
def test_postpayment_ship_receive_then_pay_completes_on_the_payment(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, payment, buyer_acc, buyer, seller_acc, seller = _awaiting_payment(db)

        _ship(db, deal, seller_acc, seller)
        assert deal.status == DealStatus.shipped, "on the direct rail goods may leave before money"
        _receive(db, deal, buyer_acc, buyer)
        assert deal.status == DealStatus.delivered, "received but unpaid is not complete"
        assert payment.status == EscrowStatus.pending

        escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        db.commit()

        assert payment.status == EscrowStatus.released
        assert deal.status == DealStatus.completed


@requires_real_db
def test_postpayment_paid_in_transit_completes_on_receipt(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, payment, buyer_acc, buyer, seller_acc, seller = _awaiting_payment(db)

        _ship(db, deal, seller_acc, seller)
        escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        assert payment.status == EscrowStatus.funded
        assert deal.status == DealStatus.shipped, "the goods are still on the road"

        _receive(db, deal, buyer_acc, buyer)
        db.commit()
        db.refresh(payment)

        assert deal.status == DealStatus.completed
        assert payment.status == EscrowStatus.released


@requires_real_db
def test_the_confirmation_is_audited_to_the_seller_account(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.models.staff import AuditLog  # noqa: PLC0415

    with sf() as db:
        _deal, payment, _b_acc, _b, seller_acc, _s = _awaiting_payment(db)
        escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        db.commit()

        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "escrow.mark_party", AuditLog.entity_id == str(payment.id))
            .one()
        )
        assert entry.details["account_id"] == seller_acc.id
        assert entry.details["to"] == "funded"


@requires_real_db
def test_confirming_twice_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415

    with sf() as db:
        _deal, payment, _b_acc, _b, seller_acc, _s = _awaiting_payment(db)
        escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        with pytest.raises(escrow_service.InvalidEscrowTransition):
            escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)


@requires_real_db
def test_a_cancelled_deal_cannot_be_marked_paid(sf) -> None:  # noqa: ANN001
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal, payment, buyer_acc, buyer, seller_acc, _s = _awaiting_payment(db)
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.cancelled, reason="передумали", company_id=buyer.id
        )
        with pytest.raises(escrow_service.InvalidEscrowTransition):
            escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_the_stub_rail_keeps_its_rules(sf) -> None:  # noqa: ANN001
    """An operator-reconciled payment is not the seller's to confirm, and its deal
    cannot ship before the money is marked."""
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, payment, _b_acc, _b, seller_acc, seller = _awaiting_payment(db, mode="stub")

        with pytest.raises(escrow_service.WrongRail):
            escrow_service.confirm_direct_payment(db, payment, account_id=seller_acc.id)
        with pytest.raises(deal_service.InvalidDealTransition):
            _ship(db, deal, seller_acc, seller)
        assert DealStatus.shipped not in deal_service.available_transitions(
            deal, DealActorKind.seller
        )
        assert escrow_service.can_confirm_direct(deal, payment) is False
