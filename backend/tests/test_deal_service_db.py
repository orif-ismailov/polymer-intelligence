"""Real-Postgres tests for deal_service (P2 W1 — T1.2 acceptance).

Guarded (localhost test_polymer). S3 is stubbed. Covers what the pure-data
transition tests cannot: the verified gate, the accept race on one RFQ (two
suppliers, one deal), the party-role rules under a real row lock, the append-only
timeline, chat authorship, and document revocation.
"""

from __future__ import annotations

import decimal
import hashlib
import threading

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_member,
    make_request,
    make_seller_offer,
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


def _stub_s3(monkeypatch) -> None:  # noqa: ANN001
    from app.services import storage_service  # noqa: PLC0415

    def fake_store(deal_id, section, content, filename):  # noqa: ANN001, ANN202
        mime = storage_service.validate_upload(content, filename)
        if mime not in storage_service.DEAL_FILE_MIMES:
            raise ValueError("invalid_file_type")
        return (
            f"deals/{deal_id}/{section}/x-{filename}",
            mime,
            hashlib.sha256(content).hexdigest(),
        )

    monkeypatch.setattr(storage_service, "store_deal_file", fake_store)


_PDF = b"%PDF-1.4 fake document body"


def _verified(db, tax, phone, **kw):  # noqa: ANN001, ANN202
    """An owner account + a verified company they own."""
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax, **kw)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _parties(db):  # noqa: ANN001, ANN202
    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
    return buyer_acc, buyer, seller_acc, seller


def _response(db, request, company, account, **kw):  # noqa: ANN001, ANN003, ANN202
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415

    row = RfqResponse(
        request_id=request.id,
        company_id=company.id,
        created_by_user_account_id=account.id,
        price=kw.pop("price", decimal.Decimal("1250.00")),
        currency=kw.pop("currency", "USD"),
        qty=kw.pop("qty", decimal.Decimal("20")),
        qty_unit="MT",
        **kw,
    )
    db.add(row)
    db.flush()
    return row


def _open_deal(db, monkeypatch=None):  # noqa: ANN001, ANN202
    """The standard fixture deal: buyer's RFQ, seller's response, accepted."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    buyer_acc, buyer, seller_acc, seller = _parties(db)
    request = make_request(db, company=buyer, account=buyer_acc)
    response = _response(db, request, seller, seller_acc)
    deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
    return deal, buyer_acc, buyer, seller_acc, seller


# ── Opening from an RFQ response ──────────────────────────────────────────────


@requires_real_db
def test_open_from_response_sets_number_amount_and_accepts(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, RfqResponseStatus  # noqa: PLC0415

    with sf() as db:
        deal, _buyer_acc, buyer, _seller_acc, seller = _open_deal(db)

        assert deal.status == DealStatus.negotiation
        assert deal.number.startswith("DEAL-")
        assert deal.buyer_company_id == buyer.id
        assert deal.seller_company_id == seller.id
        # Deal value is the TOTAL, not the unit price: 1250.00 x 20 MT.
        assert deal.amount == decimal.Decimal("25000.00")
        assert deal.currency == "USD"

        from app.domains.deals.models import RfqResponse  # noqa: PLC0415

        accepted = db.query(RfqResponse).filter(RfqResponse.request_id == deal.request_id).one()
        assert accepted.status == RfqResponseStatus.accepted
        assert accepted.deal_id == deal.id


@requires_real_db
def test_open_writes_the_opening_history_row(sf) -> None:  # noqa: ANN001
    from app.domains.deals.models import DealStatusHistory  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _open_deal(db)
        rows = (
            db.query(DealStatusHistory).filter(DealStatusHistory.deal_id == deal.id).all()
        )
        assert len(rows) == 1
        assert rows[0].from_status is None, "the opening row has nothing before it"
        assert rows[0].to_status == DealStatus.negotiation


@requires_real_db
def test_open_emits_deal_opened(sf) -> None:  # noqa: ANN001
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _open_deal(db)
        types = {e.event_type for e in db.query(DomainEvent).all()}
        assert event_types.DEAL_OPENED in types
        assert event_types.RFQ_RESPONSE_ACCEPTED in types


@requires_real_db
def test_unverified_party_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        seller.status = CompanyStatus.pending_verification
        db.flush()
        request = make_request(db, company=buyer, account=buyer_acc)
        response = _response(db, request, seller, seller_acc)
        with pytest.raises(deal_service.CompanyNotVerified):
            deal_service.open_deal_from_response(db, request, response, buyer_acc)


@requires_real_db
def test_rfq_without_a_buyer_company_cannot_become_a_deal(sf) -> None:  # noqa: ANN001
    """A Telegram-origin request has no company to make a party of."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller = _parties(db)
        tg_account = make_account(db, "+998900000009")
        request = make_request(db, account=tg_account)  # no company
        response = _response(db, request, seller, seller_acc)
        with pytest.raises(deal_service.DealRequiresCompany):
            deal_service.open_deal_from_response(db, request, response, tg_account)


@requires_real_db
def test_competing_responses_are_retired_on_accept(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415
    from app.models.enums import RfqResponseStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")
        request = make_request(db, company=buyer, account=buyer_acc)
        winner = _response(db, request, seller, seller_acc)
        loser = _response(db, request, other, other_acc, price=decimal.Decimal("1400"))

        deal_service.open_deal_from_response(db, request, winner, buyer_acc)

        db.refresh(loser)
        assert loser.status == RfqResponseStatus.not_selected
        assert loser.deal_id is None
        assert (
            db.query(RfqResponse)
            .filter(RfqResponse.status == RfqResponseStatus.accepted)
            .count()
            == 1
        )


@requires_real_db
def test_second_accept_on_the_same_rfq_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")
        request = make_request(db, company=buyer, account=buyer_acc)
        first = _response(db, request, seller, seller_acc)
        second = _response(db, request, other, other_acc)

        deal_service.open_deal_from_response(db, request, first, buyer_acc)
        db.commit()

        with pytest.raises(deal_service.ResponseNotOpen):
            # `second` was retired to not_selected by the first accept.
            deal_service.open_deal_from_response(db, request, second, buyer_acc)


@requires_real_db
def test_concurrent_accepts_produce_exactly_one_deal(sf) -> None:  # noqa: ANN001
    """Two suppliers accepted at the same instant: the FOR UPDATE lock on the
    RFQ row serializes them, so the loser sees the winner and backs out."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")
        request = make_request(db, company=buyer, account=buyer_acc)
        r1 = _response(db, request, seller, seller_acc)
        r2 = _response(db, request, other, other_acc)
        db.commit()
        request_id, r1_id, r2_id, account_id = request.id, r1.id, r2.id, buyer_acc.id

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def accept(response_id: int) -> None:
        from app.domains.deals.models import RfqResponse  # noqa: PLC0415
        from app.models.accounts import UserAccount  # noqa: PLC0415
        from app.models.requests import Request  # noqa: PLC0415

        with sf() as session:
            req = session.get(Request, request_id)
            resp = session.get(RfqResponse, response_id)
            acct = session.get(UserAccount, account_id)
            barrier.wait(timeout=10)
            try:
                deal_service.open_deal_from_response(session, req, resp, acct)
                session.commit()
                outcomes.append("won")
            except Exception as exc:  # noqa: BLE001 — the loser's rejection is the point
                session.rollback()
                outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=accept, args=(rid,)) for rid in (r1_id, r2_id)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert outcomes.count("won") == 1, outcomes
    with sf() as db:
        assert db.query(Deal).count() == 1


# ── Transitions ───────────────────────────────────────────────────────────────


@requires_real_db
def test_seller_ships_and_buyer_confirms_delivery(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, _buyer, seller_acc, _seller = _open_deal(db)
        # Walk to paid_escrow the way the system would.
        for status in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status, actor_kind=DealActorKind.system)

        deal_service.transition_by_party(db, deal, seller_acc, DealStatus.shipped)
        assert deal.status == DealStatus.shipped
        deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.delivered)
        assert deal.status == DealStatus.delivered


@requires_real_db
def test_buyer_cannot_declare_a_shipment(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, _b, _sa, _s = _open_deal(db)
        for status in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status, actor_kind=DealActorKind.system)
        with pytest.raises(deal_service.ActorNotAllowed):
            deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.shipped)


@requires_real_db
def test_a_party_cannot_forge_a_system_transition(sf) -> None:  # noqa: ANN001
    """contract_signed follows from E-IMZO activation, never from an HTTP call."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        deal_service.transition(
            db, deal, DealStatus.contract_pending, actor_kind=deal_service.DealActorKind.system
        )
        with pytest.raises(deal_service.ActorNotAllowed):
            deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.contract_signed)


@requires_real_db
def test_illegal_pair_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _open_deal(db)
        with pytest.raises(deal_service.InvalidDealTransition):
            deal_service.transition(db, deal, DealStatus.shipped, actor_kind=DealActorKind.system)


@requires_real_db
def test_cancel_requires_a_reason_and_records_it(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        with pytest.raises(deal_service.ReasonRequired):
            deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.cancelled)
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.cancelled, reason="budget pulled"
        )
        assert deal.status == DealStatus.cancelled
        assert deal.cancelled_reason == "budget pulled"


@requires_real_db
def test_no_unilateral_cancel_once_money_is_in_escrow(sf) -> None:  # noqa: ANN001
    """FR-D8: after paid_escrow the only way out is a dispute."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        for status in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status, actor_kind=DealActorKind.system)

        with pytest.raises(deal_service.InvalidDealTransition):
            deal_service.transition_by_party(
                db, deal, buyer_acc, DealStatus.cancelled, reason="changed my mind"
            )
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.disputed, reason="goods never shipped"
        )
        assert deal.status == DealStatus.disputed


@requires_real_db
def test_only_staff_resolves_a_dispute(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        for status in (
            DealStatus.contract_pending,
            DealStatus.contract_signed,
            DealStatus.payment_pending,
            DealStatus.paid_escrow,
        ):
            deal_service.transition(db, deal, status, actor_kind=DealActorKind.system)
        deal_service.transition_by_party(
            db, deal, buyer_acc, DealStatus.disputed, reason="not shipped"
        )

        with pytest.raises(deal_service.ActorNotAllowed):
            deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.paid_escrow)
        deal_service.transition(
            db, deal, DealStatus.paid_escrow, actor_kind=DealActorKind.staff, actor_id=1
        )
        assert deal.status == DealStatus.paid_escrow


@requires_real_db
def test_every_transition_appends_to_the_timeline(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import DealStatusHistory  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _open_deal(db)
        deal_service.transition(
            db, deal, DealStatus.contract_pending, actor_kind=DealActorKind.system
        )
        deal_service.transition(
            db, deal, DealStatus.contract_signed, actor_kind=DealActorKind.system
        )
        rows = (
            db.query(DealStatusHistory)
            .filter(DealStatusHistory.deal_id == deal.id)
            .order_by(DealStatusHistory.id)
            .all()
        )
        assert [(r.from_status, r.to_status) for r in rows] == [
            (None, DealStatus.negotiation),
            (DealStatus.negotiation, DealStatus.contract_pending),
            (DealStatus.contract_pending, DealStatus.contract_signed),
        ]


# ── Chat ──────────────────────────────────────────────────────────────────────


@requires_real_db
def test_message_records_the_side_that_wrote_it(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, buyer, seller_acc, seller = _open_deal(db)
        first = deal_service.post_message(db, deal, buyer_acc, "Can you ship by Friday?")
        second = deal_service.post_message(db, deal, seller_acc, "Yes.")
        assert first.author_company_id == buyer.id
        assert second.author_company_id == seller.id


@requires_real_db
def test_outsider_cannot_post(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _open_deal(db)
        outsider, _company = _verified(db, "304444444", "+998900000004")
        with pytest.raises(deal_service.NotDealParticipant):
            deal_service.post_message(db, deal, outsider, "hello")


@requires_real_db
def test_plain_member_of_a_party_is_read_only(sf) -> None:  # noqa: ANN001
    """A `member` may read the room but not speak for the company in it."""
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        deal, _buyer_acc, buyer, *_ = _open_deal(db)
        junior = make_account(db, "+998900000005")
        make_member(db, buyer, junior)  # default role: member
        assert deal_service.is_participant_account(db, deal, junior) is True
        with pytest.raises(deal_service.NotDealParticipant):
            deal_service.post_message(db, deal, junior, "hi")


@requires_real_db
def test_empty_message_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        with pytest.raises(ValueError, match="empty_message"):
            deal_service.post_message(db, deal, buyer_acc, "   ")


@requires_real_db
def test_message_with_a_file(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    _stub_s3(monkeypatch)
    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        message = deal_service.post_message(
            db, deal, buyer_acc, "", file_content=_PDF, file_name="spec.pdf"
        )
        assert message.file_storage_path is not None
        assert message.file_name == "spec.pdf"
        assert message.body == ""


@requires_real_db
def test_chat_poll_is_incremental(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        first = deal_service.post_message(db, deal, buyer_acc, "one")
        second = deal_service.post_message(db, deal, buyer_acc, "two")
        assert [m.id for m in deal_service.list_messages(db, deal)] == [first.id, second.id]
        assert [m.id for m in deal_service.list_messages(db, deal, after_id=first.id)] == [
            second.id
        ]


# ── Documents ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_document_is_hashed_and_attributed(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealDocumentKind  # noqa: PLC0415

    _stub_s3(monkeypatch)
    with sf() as db:
        deal, _buyer_acc, _buyer, seller_acc, seller = _open_deal(db)
        document = deal_service.add_document(
            db, deal, seller_acc, DealDocumentKind.invoice, _PDF, "invoice.pdf"
        )
        assert document.sha256 == hashlib.sha256(_PDF).hexdigest()
        assert document.uploaded_by_company_id == seller.id
        assert document.revoked is False


@requires_real_db
def test_document_rejects_an_unsupported_type(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealDocumentKind  # noqa: PLC0415

    _stub_s3(monkeypatch)
    with sf() as db:
        deal, buyer_acc, *_ = _open_deal(db)
        with pytest.raises(ValueError, match="invalid_file_type"):
            deal_service.add_document(
                db, deal, buyer_acc, DealDocumentKind.other, b"MZ\x90\x00 not a doc", "x.exe"
            )


@requires_real_db
def test_only_the_uploader_may_revoke(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealDocumentKind  # noqa: PLC0415

    _stub_s3(monkeypatch)
    with sf() as db:
        deal, buyer_acc, _buyer, seller_acc, _seller = _open_deal(db)
        document = deal_service.add_document(
            db, deal, seller_acc, DealDocumentKind.invoice, _PDF, "invoice.pdf"
        )
        with pytest.raises(deal_service.NotDealParticipant):
            deal_service.revoke_document(db, document, buyer_acc, "wrong file")

        deal_service.revoke_document(db, document, seller_acc, "superseded by v2")
        assert document.revoked is True
        assert document.revoked_reason == "superseded by v2"
        # The object itself is evidence and stays put.
        assert document.storage_path is not None


@requires_real_db
def test_revocation_is_not_repeatable(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import DealDocumentKind  # noqa: PLC0415

    _stub_s3(monkeypatch)
    with sf() as db:
        deal, _buyer_acc, _buyer, seller_acc, _seller = _open_deal(db)
        document = deal_service.add_document(
            db, deal, seller_acc, DealDocumentKind.other, _PDF, "x.pdf"
        )
        deal_service.revoke_document(db, document, seller_acc, "first")
        with pytest.raises(deal_service.DocumentAlreadyRevoked):
            deal_service.revoke_document(db, document, seller_acc, "second")


# ── Opening from an inquiry ───────────────────────────────────────────────────


@requires_real_db
def test_open_from_company_inquiry(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        offer = make_seller_offer(db, company=seller, created_by=seller_acc.id)
        inquiry = OfferRequest(
            offer_id=offer.id,
            company_id=buyer.id,
            created_by_user_account_id=buyer_acc.id,
            quantity=decimal.Decimal("10"),
            target_price=decimal.Decimal("900.00"),
            currency="USD",
        )
        db.add(inquiry)
        db.flush()

        deal = deal_service.open_deal_from_inquiry(db, inquiry, seller_acc)
        assert deal.status == DealStatus.negotiation
        assert deal.offer_id == offer.id
        assert deal.amount == decimal.Decimal("9000.00")


@requires_real_db
def test_telegram_inquiry_cannot_become_a_deal(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415
    from tests._verification_db import make_seller  # noqa: PLC0415

    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller = _parties(db)
        offer = make_seller_offer(db, company=seller, created_by=seller_acc.id)
        tg_seller = make_seller(db, telegram_user_id=42)
        from app.models.requests import Client  # noqa: PLC0415

        client = Client(telegram_user_id=99)
        db.add(client)
        db.flush()
        inquiry = OfferRequest(offer_id=offer.id, client_id=client.id)
        db.add(inquiry)
        db.flush()
        assert tg_seller is not None

        with pytest.raises(deal_service.DealRequiresCompany):
            deal_service.open_deal_from_inquiry(db, inquiry, seller_acc)


@requires_real_db
def test_inquiry_cannot_open_two_live_deals(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller = _parties(db)
        offer = make_seller_offer(db, company=seller, created_by=seller_acc.id)
        inquiry = OfferRequest(
            offer_id=offer.id, company_id=buyer.id, created_by_user_account_id=buyer_acc.id
        )
        db.add(inquiry)
        db.flush()

        deal_service.open_deal_from_inquiry(db, inquiry, seller_acc)
        with pytest.raises(deal_service.DealAlreadyOpen):
            deal_service.open_deal_from_inquiry(db, inquiry, seller_acc)


# ── Numbering ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_deal_numbers_are_sequential_within_the_year(sf) -> None:  # noqa: ANN001
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        first = deal_service.generate_deal_number(db)
        second = deal_service.generate_deal_number(db)
        year, seq = first.split("-")[1], first.split("-")[2]
        assert first.startswith(f"DEAL-{year}-")
        assert len(seq) == 6, "zero-padded to six digits"
        assert int(second.split("-")[2]) == int(seq) + 1
