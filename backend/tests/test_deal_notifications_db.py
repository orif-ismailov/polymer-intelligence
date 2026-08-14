"""Deal notification tests (P2 W3 — T3.1).

Guarded (localhost test_polymer). Portal bell notifications are written INLINE,
in the same transaction as the thing they announce — the precedent set by
request/inquiry notifications, and the reason a rolled-back deal never leaves a
stray bell entry. Only the Telegram staff cards go through the outbox.

The interesting rule here is the chat cooldown: a busy Trade Room would
otherwise ring the bell on every line typed.
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
    # distributor+trader: buys and sells — the role gates (T-B) require it
    company = make_company(db, account, tax_id=tax, roles=["distributor", "trader"])
    company.status = CompanyStatus.verified
    company.legal_name = f"OOO {tax}"
    db.flush()
    return account, company


def _scene(db):  # noqa: ANN001, ANN202
    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
    request = make_request(db, company=buyer, account=buyer_acc)
    return buyer_acc, buyer, seller_acc, seller, request


def _quote(db, request, company, account, price="1250.00"):  # noqa: ANN001, ANN202
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    return rfq_response_service.submit(
        db, request, company, account,
        price=decimal.Decimal(price), currency="USD",
        qty=decimal.Decimal("20"), qty_unit="MT",
    )


def _bell(db, account_id, kind=None):  # noqa: ANN001, ANN202
    from app.domains.notifications.models import PortalNotification  # noqa: PLC0415

    query = db.query(PortalNotification).filter(
        PortalNotification.user_account_id == account_id
    )
    if kind is not None:
        query = query.filter(PortalNotification.kind == kind)
    return query.order_by(PortalNotification.id).all()


# ── RFQ responses ─────────────────────────────────────────────────────────────


@requires_real_db
def test_a_new_quote_rings_the_buyers_bell(sf) -> None:  # noqa: ANN001
    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        _quote(db, request, seller, seller_acc)

        rows = _bell(db, buyer_acc.id, "rfq_response_new")
        assert len(rows) == 1
        assert rows[0].entity == "request"
        assert rows[0].entity_id == str(request.id)
        # Never pre-rendered text — the portal renders in the reader's language.
        assert rows[0].title_key == "notifications.rfq_response_new.title"


@requires_real_db
def test_the_supplier_is_not_notified_of_their_own_quote(sf) -> None:  # noqa: ANN001
    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        _quote(db, request, seller, seller_acc)
        assert _bell(db, seller_acc.id, "rfq_response_new") == []


@requires_real_db
def test_accept_notifies_the_winner_and_the_losers_differently(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")
        winner = _quote(db, request, seller, seller_acc)
        _quote(db, request, other, other_acc, price="1400.00")

        deal_service.open_deal_from_response(db, request, winner, buyer_acc)

        assert len(_bell(db, seller_acc.id, "rfq_response_accepted")) == 1
        assert len(_bell(db, other_acc.id, "rfq_response_not_selected")) == 1
        assert _bell(db, other_acc.id, "rfq_response_accepted") == []


@requires_real_db
def test_opening_a_deal_notifies_both_sides(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)

        for account in (buyer_acc, seller_acc):
            rows = _bell(db, account.id, "deal_opened")
            assert len(rows) == 1, f"account {account.id}"
            assert rows[0].entity == "deal"
            assert rows[0].entity_id == str(deal.id)
            assert rows[0].params["number"] == deal.number


@requires_real_db
def test_every_active_member_of_a_party_is_notified(sf) -> None:  # noqa: ANN001
    """A plain member reads the room, so they get the bell too."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller, request = _scene(db)
        junior = make_account(db, "+998900000004")
        make_member(db, buyer, junior)
        response = _quote(db, request, seller, seller_acc)
        deal_service.open_deal_from_response(db, request, response, buyer_acc)

        assert len(_bell(db, junior.id, "deal_opened")) == 1


# ── status changes ────────────────────────────────────────────────────────────


@requires_real_db
def test_a_party_transition_notifies_the_other_side_only(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        for status_ in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)

        before = len(_bell(db, seller_acc.id, "deal_status"))
        deal_service.transition_by_party(db, deal, seller_acc, DealStatus.shipped)

        assert len(_bell(db, buyer_acc.id, "deal_status")) >= 1, "the buyer hears about it"
        assert len(_bell(db, seller_acc.id, "deal_status")) == before, (
            "the side that acted does not need telling"
        )


@requires_real_db
def test_a_system_transition_notifies_both_sides(sf) -> None:  # noqa: ANN001
    """Nobody clicked, so nobody already knows."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        deal_service.transition(
            db, deal, DealStatus.contract_pending, actor_kind=DealActorKind.system
        )

        assert len(_bell(db, buyer_acc.id, "deal_status")) == 1
        assert len(_bell(db, seller_acc.id, "deal_status")) == 1


# ── chat + documents ──────────────────────────────────────────────────────────


@requires_real_db
def test_chat_notification_has_a_cooldown(sf) -> None:  # noqa: ANN001
    """A busy room must not ring the bell on every line typed."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)

        for i in range(5):
            deal_service.post_message(db, deal, buyer_acc, f"line {i}")

        assert len(_bell(db, seller_acc.id, "deal_message")) == 1


@requires_real_db
def test_the_cooldown_survives_the_reader_opening_the_bell(sf) -> None:  # noqa: ANN001
    """Plain unread-dedup would fire again the moment the counterparty reads it;
    the cooldown is a time window, so it does not."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)

        deal_service.post_message(db, deal, buyer_acc, "first")
        notification_service.mark_read(db, seller_acc.id, mark_all=True)
        deal_service.post_message(db, deal, buyer_acc, "second")

        assert len(_bell(db, seller_acc.id, "deal_message")) == 1


@requires_real_db
def test_the_cooldown_is_per_deal(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        first = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        offer = SellerOffer(company_id=seller.id, product_text="LDPE")
        db.add(offer)
        db.flush()
        second = deal_service._open(
            db, buyer=buyer, seller=seller, account=buyer_acc, offer_id=offer.id
        )

        deal_service.post_message(db, first, buyer_acc, "about the first")
        deal_service.post_message(db, second, buyer_acc, "about the second")

        assert len(_bell(db, seller_acc.id, "deal_message")) == 2


@requires_real_db
def test_the_author_is_not_notified_of_their_own_message(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        deal_service.post_message(db, deal, buyer_acc, "hello")

        assert _bell(db, buyer_acc.id, "deal_message") == []


@requires_real_db
def test_a_document_notifies_the_other_side(sf) -> None:  # noqa: ANN001
    import hashlib  # noqa: PLC0415

    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealDocumentKind  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)

        original = storage_service.store_deal_file
        storage_service.store_deal_file = (  # type: ignore[assignment]
            lambda d, s, c, f: (f"deals/{d}/{s}/x", "application/pdf", hashlib.sha256(c).hexdigest())
        )
        try:
            deal_service.add_document(
                db, deal, seller_acc, DealDocumentKind.invoice, b"%PDF-1.4 x", "inv.pdf"
            )
        finally:
            storage_service.store_deal_file = original  # type: ignore[assignment]

        assert len(_bell(db, buyer_acc.id, "deal_document")) == 1
        assert _bell(db, seller_acc.id, "deal_document") == []


# ── rollback safety ───────────────────────────────────────────────────────────


@requires_real_db
def test_a_rolled_back_deal_leaves_no_bell_entry(sf) -> None:  # noqa: ANN001
    """Inline notification means the bell shares the deal's fate."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.notifications.models import PortalNotification  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _buyer, seller_acc, seller, request = _scene(db)
        response = _quote(db, request, seller, seller_acc)
        deal_service.open_deal_from_response(db, request, response, buyer_acc)
        db.rollback()

    with sf() as db:
        assert db.query(PortalNotification).count() == 0


# ── Telegram staff cards (outbox) ─────────────────────────────────────────────


def test_staff_card_consumers_are_registered() -> None:
    """No DB: the card only fires if the consumer is actually wired."""
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415
    from app.tasks.notify import (  # noqa: PLC0415
        send_deal_opened_to_group,
        send_deal_status_to_group,
    )

    assert send_deal_opened_to_group in CONSUMERS[event_types.DEAL_OPENED]
    assert send_deal_status_to_group in CONSUMERS[event_types.DEAL_STATUS_CHANGED]


def test_staff_status_card_only_fires_for_disputes() -> None:
    """Every status change emits DEAL_STATUS_CHANGED; the staff group only wants
    the ones that need a human."""
    from app.tasks.notify import send_deal_status_to_group  # noqa: PLC0415

    result = send_deal_status_to_group(
        event_id=None, aggregate_id="1", payload={"to": "shipped"}
    )
    assert result["status"] == "skipped"
