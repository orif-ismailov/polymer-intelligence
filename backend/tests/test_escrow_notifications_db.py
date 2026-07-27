"""Escrow notification tests (P3 W2 — T2.4).

Guarded (localhost test_polymer). Same split as P2: portal bells are written
INLINE, in the same transaction as the money movement they announce, so a
rolled-back mark leaves no bell claiming money moved. Only the Telegram staff
card goes through the outbox.

The rule that matters here is that money notifications are NOT deduped. Every
other bell in the product suppresses an identical unread duplicate; two distinct
escrow movements on one deal are not duplicates, and swallowing the second would
mean a party is never told their money was released.
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
    make_member,
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


def _verified(db, tax, phone):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _signed_deal(db):  # noqa: ANN001, ANN202
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

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
    return deal, buyer_acc, buyer, seller_acc, seller


def _bells(db, kind):  # noqa: ANN001, ANN202
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    return db.query(PortalNotification).filter(PortalNotification.kind == kind).all()


# ── portal bells ──────────────────────────────────────────────────────────────


@requires_real_db
def test_raising_the_invoice_rings_both_bells(sf) -> None:  # noqa: ANN001
    from app.services import escrow_service, notification_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _signed_deal(db)
        escrow_service.open_for_deal(db, deal)
        db.commit()

        rung = _bells(db, notification_service.KIND_ESCROW_OPENED)
        assert {n.user_account_id for n in rung} == {buyer_acc.id, seller_acc.id}
        assert rung[0].entity == "deal"
        assert rung[0].entity_id == str(deal.id)
        assert rung[0].params["amount"] == "25000.00"
        assert rung[0].params["currency"] == "USD"
        assert buyer.id and seller.id  # both parties exist


@requires_real_db
def test_every_movement_rings_both_bells(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.services import (  # noqa: PLC0415
        deal_service,
        escrow_service,
        notification_service,
    )

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _signed_deal(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        deal_service.transition_by_party(
            db, deal, seller_acc, DealStatus.shipped, company_id=seller.id
        )
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.delivered, company_id=buyer.id
        )
        escrow_service.mark(db, payment, EscrowStatus.released, staff_user=staff, note="out")
        db.commit()

        rung = _bells(db, notification_service.KIND_ESCROW_STATUS)
        # Two movements x two parties. Nothing is deduped away: "your money
        # arrived" and "your money was paid out" are different sentences.
        assert len(rung) == 4, [n.params for n in rung]
        statuses = {n.params["status"] for n in rung}
        assert statuses == {"funded", "released"}


@requires_real_db
def test_a_rolled_back_mark_leaves_no_bell(sf) -> None:  # noqa: ANN001
    """The bell shares the movement's fate: nobody may be told money moved when
    the transaction that moved it was discarded."""
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _signed_deal(db)
        staff = make_staff(db)
        payment = escrow_service.open_for_deal(db, deal)
        escrow_service.mark(db, payment, EscrowStatus.funded, staff_user=staff, note="in")
        db.commit()
        before = db.query(PortalNotification).count()

        # A refund out of funded escrow needs a dispute first — this fails.
        with pytest.raises(Exception):  # noqa: B017, PT011 — any refusal will do
            escrow_service.mark(
                db, payment, EscrowStatus.refunded, staff_user=staff, note="give it back"
            )
        db.rollback()

        assert db.query(PortalNotification).count() == before


@requires_real_db
def test_the_bell_names_the_deal_so_the_portal_can_link_to_it(sf) -> None:  # noqa: ANN001
    from app.services import escrow_service, notification_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _signed_deal(db)
        escrow_service.open_for_deal(db, deal)
        db.commit()

        bell = _bells(db, notification_service.KIND_ESCROW_OPENED)[0]
        assert bell.params["deal_id"] == deal.id
        assert bell.params["number"] == deal.number
        assert bell.title_key == "notifications.escrow_opened.title"
        assert bell.body_key == "notifications.escrow_opened.body"


@requires_real_db
def test_every_active_member_of_both_parties_hears_about_money(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415
    from app.services import escrow_service, notification_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _signed_deal(db)
        colleague = make_account(db, "+998900000009")
        make_member(db, buyer, colleague, role=CompanyMemberRole.manager)
        dormant = make_account(db, "+998900000010")
        make_member(db, seller, dormant, status=CompanyMemberStatus.invited)

        escrow_service.open_for_deal(db, deal)
        db.commit()

        rung = {n.user_account_id for n in _bells(db, notification_service.KIND_ESCROW_OPENED)}
        assert rung == {buyer_acc.id, seller_acc.id, colleague.id}
        assert dormant.id not in rung, "an invited-but-inactive member is not a party yet"


# ── Telegram staff card (outbox) ──────────────────────────────────────────────


def test_the_funded_card_consumer_is_registered() -> None:
    """No DB: the card only fires if the consumer is actually wired."""
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415
    from app.tasks.notify import send_escrow_funded_to_group  # noqa: PLC0415

    assert send_escrow_funded_to_group in CONSUMERS[event_types.ESCROW_FUNDED]


def test_only_funding_reaches_the_staff_group() -> None:
    """Opening an invoice and paying out are routine; money ARRIVING is what the
    operators act on. The other three escrow events carry no card."""
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415
    from app.tasks.notify import send_escrow_funded_to_group  # noqa: PLC0415

    for event_type in (
        event_types.ESCROW_OPENED,
        event_types.ESCROW_RELEASED,
        event_types.ESCROW_REFUNDED,
    ):
        assert send_escrow_funded_to_group not in CONSUMERS[event_type]


def test_a_card_for_a_missing_deal_never_raises() -> None:
    """Fail-soft: a bot or DB hiccup must not wedge the outbox."""
    from app.tasks.notify import send_escrow_funded_to_group  # noqa: PLC0415

    assert send_escrow_funded_to_group(event_id=None, aggregate_id="1", payload={})[
        "status"
    ] in {"skipped", "error"}
