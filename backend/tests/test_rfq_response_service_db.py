"""Real-Postgres tests for rfq_response_service (P2 W1 — T1.3 + T1.35).

Guarded (localhost test_polymer). Covers the supplier side of an RFQ: who may
respond at all (verified, not the buyer themselves, RFQ still open and visible to
them), the one-live-response rule and how withdrawing frees it, and the FR-D10
visibility gate in both directions — the guard on submit AND the market-list
query that must not show a supplier an RFQ they could not answer.
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
    # distributor+trader: these fixtures both file RFQs and quote against them,
    # and the role gates (T-B) require a seller role for the latter
    company = make_company(db, account, tax_id=tax, roles=["distributor", "trader"])
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _setup(db):  # noqa: ANN001, ANN202
    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
    request = make_request(db, company=buyer, account=buyer_acc)
    return buyer_acc, buyer, seller_acc, seller, request


_QUOTE = {
    "price": decimal.Decimal("1250.00"),
    "currency": "USD",
    "qty": decimal.Decimal("20"),
    "qty_unit": "MT",
}


# ── Submitting ────────────────────────────────────────────────────────────────


@requires_real_db
def test_submit_happy_path(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqResponseStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        response = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)

        assert response.status == RfqResponseStatus.submitted
        assert response.deal_id is None
        assert response.company_id == seller.id
        types = {e.event_type for e in db.query(DomainEvent).all()}
        assert event_types.RFQ_RESPONSE_SUBMITTED in types


@requires_real_db
def test_unverified_supplier_cannot_respond(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        seller.status = CompanyStatus.pending_verification
        db.flush()
        with pytest.raises(deal_service.CompanyNotVerified):
            rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)


@requires_real_db
def test_buyer_cannot_respond_to_their_own_rfq(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, _s, request = _setup(db)
        with pytest.raises(rfq_response_service.CannotRespondOwnRequest):
            rfq_response_service.submit(db, request, buyer, buyer_acc, **_QUOTE)


@requires_real_db
def test_second_response_from_the_same_company_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        with pytest.raises(rfq_response_service.AlreadyResponded):
            rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)


@requires_real_db
def test_the_session_survives_a_duplicate(sf) -> None:  # noqa: ANN001
    """The unique-violation must not poison the surrounding transaction."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        with pytest.raises(rfq_response_service.AlreadyResponded):
            rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        # Still usable — no PendingRollbackError.
        assert rfq_response_service.list_for_request(db, request).__len__() == 1
        db.commit()


@requires_real_db
def test_withdrawing_frees_the_slot(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqResponseStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        first = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        rfq_response_service.withdraw(db, first, seller_acc)
        assert first.status == RfqResponseStatus.withdrawn

        # The partial unique index ignores withdrawn rows, so a better quote fits.
        second = rfq_response_service.submit(
            db, request, seller, seller_acc, **{**_QUOTE, "price": decimal.Decimal("1180")}
        )
        assert second.id != first.id
        assert second.status == RfqResponseStatus.submitted


@requires_real_db
def test_only_the_author_company_may_withdraw(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        outsider_acc, _outsider = _verified(db, "303333333", "+998900000003")
        response = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        with pytest.raises(rfq_response_service.NotResponseAuthor):
            rfq_response_service.withdraw(db, response, outsider_acc)


@requires_real_db
def test_cannot_withdraw_after_acceptance(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, _b, seller_acc, seller, request = _setup(db)
        response = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        deal_service.open_deal_from_response(db, request, response, buyer_acc)
        with pytest.raises(deal_service.ResponseNotOpen):
            rfq_response_service.withdraw(db, response, seller_acc)


@requires_real_db
def test_closed_rfq_takes_no_responses(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        request.status = RequestStatus.closed
        db.flush()
        with pytest.raises(rfq_response_service.RequestNotOpen):
            rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)


# ── Visibility (FR-D10) ───────────────────────────────────────────────────────


@requires_real_db
def test_verified_only_is_the_default(sf) -> None:  # noqa: ANN001
    from app.models.enums import RfqVisibility  # noqa: PLC0415

    with sf() as db:
        *_rest, request = _setup(db)
        assert request.visibility == RfqVisibility.verified_only


@requires_real_db
def test_unverified_company_cannot_see_a_verified_only_rfq(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, _sa, seller, request = _setup(db)
        seller.status = CompanyStatus.draft
        db.flush()
        assert rfq_response_service.is_visible_to(request, seller) is False


@requires_real_db
def test_selected_visibility_admits_only_the_listed_companies(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqVisibility  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        outsider_acc, outsider = _verified(db, "303333333", "+998900000003")
        request.visibility = RfqVisibility.selected
        request.visible_company_ids = [seller.id]
        db.flush()

        assert rfq_response_service.is_visible_to(request, seller) is True
        assert rfq_response_service.is_visible_to(request, outsider) is False
        with pytest.raises(rfq_response_service.RfqNotVisible):
            rfq_response_service.submit(db, request, outsider, outsider_acc, **_QUOTE)
        # And the admitted supplier is genuinely admitted.
        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)


@requires_real_db
def test_visibility_all_admits_an_unverified_company(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus, RfqVisibility  # noqa: PLC0415

    with sf() as db:
        _ba, _b, _sa, seller, request = _setup(db)
        seller.status = CompanyStatus.draft
        request.visibility = RfqVisibility.all
        db.flush()
        assert seller.status == CompanyStatus.draft
        assert rfq_response_service.is_visible_to(request, seller) is True


@requires_real_db
def test_market_list_hides_what_the_supplier_may_not_answer(sf) -> None:  # noqa: ANN001
    """The query and the submit guard must agree — otherwise the UI offers a
    'Respond' button that the API then refuses."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqVisibility  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, own = _setup(db)
        # Three more RFQs from the same buyer with different visibilities.
        wide = make_request(db, company=buyer, account=buyer_acc, number="REQ-WIDE", n=2)
        wide.visibility = RfqVisibility.all
        picked = make_request(db, company=buyer, account=buyer_acc, number="REQ-PICK", n=3)
        picked.visibility = RfqVisibility.selected
        picked.visible_company_ids = [seller.id]
        hidden = make_request(db, company=buyer, account=buyer_acc, number="REQ-HIDE", n=4)
        hidden.visibility = RfqVisibility.selected
        hidden.visible_company_ids = [buyer.id]
        db.flush()

        visible = {r.id for r in rfq_response_service.list_open_requests(db, seller)}
        assert own.id in visible and wide.id in visible and picked.id in visible
        assert hidden.id not in visible

        # Every listed RFQ must actually accept a response from this supplier.
        for request in rfq_response_service.list_open_requests(db, seller):
            assert rfq_response_service.is_visible_to(request, seller) is True


@requires_real_db
def test_market_list_pages_over_the_visible_set(sf) -> None:  # noqa: ANN001
    """A page must be full of things the supplier can answer.

    Filtering visibility after LIMIT (rather than in SQL) silently under-fills
    pages whenever hidden RFQs are interleaved — asking for 2 returns 1.
    """
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqVisibility  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, _own = _setup(db)
        # Interleave hidden RFQs between visible ones, newest last.
        for i in range(6):
            request = make_request(
                db, company=buyer, account=buyer_acc, number=f"REQ-P{i}", n=10 + i
            )
            if i % 2 == 0:
                request.visibility = RfqVisibility.selected
                request.visible_company_ids = [buyer.id]  # hidden from the seller
        db.flush()

        page = rfq_response_service.list_open_requests(db, seller, limit=2)
        assert len(page) == 2
        assert all(rfq_response_service.is_visible_to(r, seller) for r in page)

        second = rfq_response_service.list_open_requests(db, seller, limit=2, offset=2)
        assert {r.id for r in page}.isdisjoint({r.id for r in second}), "pages overlap"


@requires_real_db
def test_market_list_excludes_the_viewers_own_rfqs(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        _ba, buyer, _sa, _seller, own = _setup(db)
        assert own.id not in {r.id for r in rfq_response_service.list_open_requests(db, buyer)}


@requires_real_db
def test_market_list_excludes_closed_rfqs(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, _sa, seller, request = _setup(db)
        request.status = RequestStatus.cancelled
        db.flush()
        assert request.id not in {
            r.id for r in rfq_response_service.list_open_requests(db, seller)
        }


# ── Market-list filters ───────────────────────────────────────────────────────
#
# The filters narrow the visible set IN SQL, like visibility does: the list is
# paged, so filtering a page in the browser would silently miss matches beyond it.


def _product(db, code: str) -> int:  # noqa: ANN001
    """A catalog row to point a tender at — `clean()` leaves `products` alone and
    the test database is not seeded, so upsert one by code."""
    return int(
        db.execute(
            sa.text(
                "INSERT INTO products (code, name_ru) VALUES (:code, :code) "
                "ON CONFLICT (code) DO UPDATE SET name_ru = EXCLUDED.name_ru RETURNING id"
            ),
            {"code": code},
        ).scalar_one()
    )


@requires_real_db
def test_market_list_filters_by_product(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, other = _setup(db)
        pp, hdpe = _product(db, "TST-PP"), _product(db, "TST-HDPE")
        other.product_id = hdpe
        wanted = make_request(db, company=buyer, account=buyer_acc, number="REQ-PP", n=2)
        wanted.product_id = pp
        db.flush()

        listed = rfq_response_service.list_open_requests(db, seller, product_id=pp)
        assert [r.id for r in listed] == [wanted.id]


@requires_real_db
def test_market_list_closing_soon_is_the_last_three_days(sf) -> None:  # noqa: ANN001
    """«Скоро закрываются» is exactly the tenders the list paints amber or red:
    three days or less left, and not already past their window."""
    import datetime as dt  # noqa: PLC0415

    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, fresh = _setup(db)
        now = dt.datetime.now(dt.UTC)
        fresh.validity_days = 30
        closing = make_request(db, company=buyer, account=buyer_acc, number="REQ-SOON", n=2)
        closing.validity_days = 30
        closing.created_at = now - dt.timedelta(days=28)  # two days left
        last_day = make_request(db, company=buyer, account=buyer_acc, number="REQ-LAST", n=3)
        last_day.validity_days = 30
        last_day.created_at = now - dt.timedelta(days=29, hours=20)
        four_left = make_request(db, company=buyer, account=buyer_acc, number="REQ-FOUR", n=4)
        four_left.validity_days = 30
        four_left.created_at = now - dt.timedelta(days=26)
        expired = make_request(db, company=buyer, account=buyer_acc, number="REQ-PAST", n=5)
        expired.validity_days = 30
        expired.created_at = now - dt.timedelta(days=31)
        db.flush()

        listed = {r.id for r in rfq_response_service.list_open_requests(db, seller, closing_soon=True)}
        assert listed == {closing.id, last_day.id}


@requires_real_db
def test_market_list_urgent_only(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import Urgency  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, normal = _setup(db)
        urgent = make_request(db, company=buyer, account=buyer_acc, number="REQ-URG", n=2)
        urgent.urgency = Urgency.high
        db.flush()

        listed = rfq_response_service.list_open_requests(db, seller, urgent=True)
        assert [r.id for r in listed] == [urgent.id]
        assert normal.id in {r.id for r in rfq_response_service.list_open_requests(db, seller)}


@requires_real_db
def test_market_list_unanswered_hides_live_quotes_only(sf) -> None:  # noqa: ANN001
    """A withdrawn quote frees the tender to be answered again, so it is back in
    «Без моего ответа» — the same rule as the one-live-response slot."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller, quoted = _setup(db)
        withdrawn = make_request(db, company=buyer, account=buyer_acc, number="REQ-WD", n=2)
        untouched = make_request(db, company=buyer, account=buyer_acc, number="REQ-NEW", n=3)
        rfq_response_service.submit(db, quoted, seller, seller_acc, **_QUOTE)
        pulled = rfq_response_service.submit(db, withdrawn, seller, seller_acc, **_QUOTE)
        rfq_response_service.withdraw(db, pulled, seller_acc)

        listed = {r.id for r in rfq_response_service.list_open_requests(db, seller, unanswered=True)}
        assert listed == {withdrawn.id, untouched.id}


@requires_real_db
def test_market_list_filters_combine(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import Urgency  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, _sa, seller, plain = _setup(db)
        pp = _product(db, "TST-PP")
        plain.product_id = pp
        both = make_request(db, company=buyer, account=buyer_acc, number="REQ-BOTH", n=2)
        both.product_id = pp
        both.urgency = Urgency.high
        db.flush()

        listed = rfq_response_service.list_open_requests(db, seller, product_id=pp, urgent=True)
        assert [r.id for r in listed] == [both.id]


# ── Required documents (FR-D10) ───────────────────────────────────────────────


@requires_real_db
def test_required_docs_keep_only_known_codes(sf) -> None:  # noqa: ANN001
    from app.domains.deals.models import normalize_required_docs  # noqa: PLC0415

    assert normalize_required_docs(["coa", "sds", "coa", "nonsense"]) == ["coa", "sds"]
    assert normalize_required_docs([]) is None
    assert normalize_required_docs(None) is None


# ── Listing responses ─────────────────────────────────────────────────────────


@requires_real_db
def test_supplier_sees_only_their_own_response(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")
        mine = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        rfq_response_service.submit(db, request, other, other_acc, **_QUOTE)

        assert len(rfq_response_service.list_for_request(db, request)) == 2
        supplier_view = rfq_response_service.list_for_request(
            db, request, viewer_company_id=seller.id
        )
        assert [r.id for r in supplier_view] == [mine.id], (
            "a supplier must never see a competitor's price"
        )


@requires_real_db
def test_list_for_company_keeps_every_quote_the_open_list_drops(sf) -> None:  # noqa: ANN001
    """A supplier's own work survives the tender closing.

    `list_open_requests` is filtered to OPEN_STATUSES, so an awarded or closed
    tender takes the supplier's quote off their screen with it. This list is the
    one place it persists — and it carries the tender so the row is readable.
    """
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller, request = _setup(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")

        first = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        second_request = make_request(db, company=buyer, account=buyer_acc, n=2)
        second = rfq_response_service.submit(db, second_request, seller, seller_acc, **_QUOTE)
        # A competitor's quote on the same tender must not leak into our list.
        rfq_response_service.submit(db, request, other, other_acc, **_QUOTE)

        # The buyer closes the first tender: it leaves the open list…
        request.status = RequestStatus.closed
        db.flush()
        assert request.id not in {
            r.id for r in rfq_response_service.list_open_requests(db, seller)
        }

        # …and the quote on it is still here, newest first, with its tender.
        rows = rfq_response_service.list_for_company(db, seller)
        assert [response.id for response, _ in rows] == [second.id, first.id]
        assert {req.id for _, req in rows} == {second_request.id, request.id}


@requires_real_db
def test_list_for_company_covers_every_status(sf) -> None:  # noqa: ANN001
    """Including the two outcomes a supplier most wants to look back at."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqResponseStatus  # noqa: PLC0415

    with sf() as db:
        buyer_acc, buyer, seller_acc, seller, request = _setup(db)
        withdrawn = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        rfq_response_service.withdraw(db, withdrawn, seller_acc)
        # Withdrawing frees the partial-unique slot, so a second quote is legal.
        live = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        live.status = RfqResponseStatus.not_selected
        db.flush()

        statuses = {
            response.status for response, _ in rfq_response_service.list_for_company(db, seller)
        }
        assert statuses == {RfqResponseStatus.withdrawn, RfqResponseStatus.not_selected}


@requires_real_db
def test_list_for_company_filters_by_status(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RfqResponseStatus  # noqa: PLC0415

    with sf() as db:
        _ba, _b, seller_acc, seller, request = _setup(db)
        withdrawn = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        rfq_response_service.withdraw(db, withdrawn, seller_acc)
        live = rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)

        rows = rfq_response_service.list_for_company(
            db, seller, status=RfqResponseStatus.submitted
        )
        assert [response.id for response, _ in rows] == [live.id]


# ── The tender's own status timeline (IMEX-6) ─────────────────────────────────
#
# A quote arriving is the buyer-visible event that the tender list is built on.
# Before this, an RFQ stayed `new` however many quotes were sitting in it, so a
# buyer could not tell an untouched tender from one awaiting their decision.


@requires_real_db
def test_first_quote_moves_the_rfq_to_offer_sent(sf) -> None:  # noqa: ANN001
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller, request = _setup(db)
        assert request.status == RequestStatus.new, "precondition: nobody has triaged it"

        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)

        assert request.status == RequestStatus.offer_sent


@requires_real_db
def test_first_quote_writes_one_history_row(sf) -> None:  # noqa: ANN001
    """`new -> offer_sent` directly: walking the staff ladder would fabricate
    `viewed`/`in_progress` rows for a triage that never happened."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.domains.requests.models import RequestStatusHistory  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller, request = _setup(db)
        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)

        rows = (
            db.query(RequestStatusHistory)
            .filter(RequestStatusHistory.request_id == request.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].from_status == RequestStatus.new
        assert rows[0].to_status == RequestStatus.offer_sent
        assert rows[0].changed_by is None, "the supplier is not staff"


@requires_real_db
def test_second_quote_does_not_re_transition(sf) -> None:  # noqa: ANN001
    """`offer_sent -> offer_sent` is not in the machine, so a second quote must
    be a no-op rather than a ValueError — and must not notify the buyer twice
    about a status that did not change."""
    from app.domains.deals import rfq as rfq_response_service  # noqa: PLC0415
    from app.domains.requests.models import RequestStatusHistory  # noqa: PLC0415
    from app.models.enums import RequestStatus  # noqa: PLC0415

    with sf() as db:
        _buyer_acc, _buyer, seller_acc, seller, request = _setup(db)
        other_acc, other = _verified(db, "303333333", "+998900000003")

        rfq_response_service.submit(db, request, seller, seller_acc, **_QUOTE)
        rfq_response_service.submit(db, request, other, other_acc, **_QUOTE)

        assert request.status == RequestStatus.offer_sent
        rows = (
            db.query(RequestStatusHistory)
            .filter(RequestStatusHistory.request_id == request.id)
            .all()
        )
        assert len(rows) == 1, "one transition happened, not two"
