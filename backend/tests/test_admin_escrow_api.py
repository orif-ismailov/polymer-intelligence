"""Staff escrow API tests (P3 W2 — T2.2).

Route registration is DB-free. Behaviour runs against test_polymer (guarded).

Marking money is the most consequential button in the product, so the authz here
is deliberately tighter than the rest of the admin surface: an analyst may WATCH
the queue but not move a payment, and even an admin must send an explicit
confirmation flag — the dashboard's checkbox means nothing if the API accepts a
mark without it.
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_request,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_A = "/api/v1/admin"


def test_routes_registered() -> None:
    from app.api.admin_escrow import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/escrow" in paths
    assert "/admin/escrow/{payment_id}/mark" in paths


def test_there_is_no_delete_or_edit_path() -> None:
    """A payment record is evidence. It is marked forward, never rewritten."""
    from app.api.admin_escrow import router  # noqa: PLC0415

    methods = {m for r in router.routes for m in r.methods}  # type: ignore[attr-defined]
    assert methods <= {"GET", "POST"}, f"unexpected methods: {methods}"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _staff_headers(session, role, email):  # noqa: ANN001, ANN202
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.enums import StaffRole  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.role = StaffRole(role)
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"}


def _scene(session, *, amount=decimal.Decimal("25000.00"), open_escrow: bool = True):  # noqa: ANN001, ANN202
    """A deal at contract_signed, optionally with its escrow already raised."""
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import CompanyStatus, DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import deal_service, escrow_service  # noqa: PLC0415

    with session() as db:
        buyer_acc = make_account(db, "+998900000001")
        seller_acc = make_account(db, "+998900000002")
        buyer = company_service.create_company(db, buyer_acc, "UZ", "301111111")
        seller = company_service.create_company(db, seller_acc, "UZ", "302222222")
        for company in (buyer, seller):
            company.status = CompanyStatus.verified
            company.legal_name = f"OOO {company.tax_id}"
        db.flush()

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
        for status_ in (DealStatus.contract_pending, DealStatus.contract_signed):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)

        payment_id = None
        if open_escrow:
            payment_id = escrow_service.open_for_deal(db, deal).id
        db.commit()
        return {
            "deal_id": deal.id,
            "payment_id": payment_id,
            "buyer_co": buyer.id,
            "seller_co": seller.id,
            "buyer_acc": buyer_acc.id,
            "seller_acc": seller_acc.id,
        }


def _mark(client, headers, payment_id, to_status, **kw):  # noqa: ANN001, ANN003, ANN202
    body = {"to_status": to_status, "note": kw.pop("note", "bank ref 4821"), "confirmed": True}
    body.update(kw)
    return client.post(f"{_A}/escrow/{payment_id}/mark", json=body, headers=headers)


# ── queue ─────────────────────────────────────────────────────────────────────


@requires_real_db
def test_analyst_sees_the_queue_with_both_parties_named(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "analyst", "a@example.com")

    response = client.get(f"{_A}/escrow", headers=headers)
    assert response.status_code == 200
    body = response.json()
    item = next(i for i in body["items"] if i["id"] == scene["payment_id"])
    assert item["status"] == "pending"
    assert item["amount"] == "25000.00", "money crosses the wire as a string, not a float"
    assert item["buyer_name"] == "OOO 301111111"
    assert item["seller_name"] == "OOO 302222222"
    assert item["deal_number"].startswith("DEAL-")


@requires_real_db
def test_queue_filters_by_status(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "b@example.com")

    assert len(client.get(f"{_A}/escrow?status=pending", headers=headers).json()["items"]) == 1
    assert client.get(f"{_A}/escrow?status=funded", headers=headers).json()["items"] == []

    _mark(client, headers, scene["payment_id"], "funded")
    assert client.get(f"{_A}/escrow?status=pending", headers=headers).json()["items"] == []
    assert len(client.get(f"{_A}/escrow?status=funded", headers=headers).json()["items"]) == 1


@requires_real_db
def test_an_unknown_status_filter_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    _scene(session)
    headers = _staff_headers(session, "admin", "c@example.com")
    assert client.get(f"{_A}/escrow?status=nonsense", headers=headers).status_code == 422


@requires_real_db
def test_the_queue_surfaces_deals_stuck_without_an_invoice(api) -> None:  # noqa: ANN001
    """A signed deal with no agreed total cannot be invoiced, and the consumer
    only logs it. Without this list staff would have no way to find it."""
    client, session = api
    scene = _scene(session, amount=None, open_escrow=False)
    headers = _staff_headers(session, "admin", "d@example.com")

    body = client.get(f"{_A}/escrow", headers=headers).json()
    assert body["items"] == []
    blocked = body["blocked"]
    assert [b["deal_id"] for b in blocked] == [scene["deal_id"]]
    assert blocked[0]["reason"] == "no_amount"


@requires_real_db
def test_counters_split_the_two_waiting_queues(api) -> None:  # noqa: ANN001
    """The operator's day: who owes us money, and who do we owe money to."""
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "e@example.com")

    counters = client.get(f"{_A}/escrow", headers=headers).json()["counters"]
    assert counters["awaiting_funds"] == 1
    assert counters["awaiting_payout"] == 0

    _mark(client, headers, scene["payment_id"], "funded")
    counters = client.get(f"{_A}/escrow", headers=headers).json()["counters"]
    assert counters["awaiting_funds"] == 0
    assert counters["awaiting_payout"] == 1


# ── authz ─────────────────────────────────────────────────────────────────────


@requires_real_db
def test_an_analyst_may_watch_but_not_move_money(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "analyst", "f@example.com")

    assert client.get(f"{_A}/escrow", headers=headers).status_code == 200
    assert _mark(client, headers, scene["payment_id"], "funded").status_code == 403


@requires_real_db
def test_anonymous_gets_nothing(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    assert client.get(f"{_A}/escrow").status_code == 401
    assert (
        client.post(
            f"{_A}/escrow/{scene['payment_id']}/mark",
            json={"to_status": "funded", "note": "x", "confirmed": True},
        ).status_code
        == 401
    )


# ── marking ───────────────────────────────────────────────────────────────────


@requires_real_db
def test_marking_funded_moves_the_deal(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "g@example.com")

    response = _mark(client, headers, scene["payment_id"], "funded", note="MT103 44821")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "funded"
    assert body["funded_at"] is not None
    assert body["note"] == "MT103 44821"
    assert body["deal_status"] == "paid_escrow"


@requires_real_db
def test_an_unconfirmed_mark_is_refused(api) -> None:  # noqa: ANN001
    """The dashboard shows a checkbox — "I confirm the funds actually moved in the
    bank". A UI-only confirmation is no confirmation at all, so the API requires
    the flag too."""
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "h@example.com")

    response = _mark(client, headers, scene["payment_id"], "funded", confirmed=False)
    assert response.status_code == 422
    assert response.json()["detail"] == "confirmation_required"


@requires_real_db
def test_a_note_is_required(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "i@example.com")

    assert _mark(client, headers, scene["payment_id"], "funded", note="").status_code == 422
    assert _mark(client, headers, scene["payment_id"], "funded", note="   ").status_code == 422


@requires_real_db
def test_an_impossible_escrow_move_is_a_conflict(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "j@example.com")

    response = _mark(client, headers, scene["payment_id"], "released")
    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_transition"


@requires_real_db
def test_releasing_before_delivery_is_a_conflict_with_its_own_reason(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "k@example.com")

    _mark(client, headers, scene["payment_id"], "funded")
    response = _mark(client, headers, scene["payment_id"], "released")
    assert response.status_code == 409
    assert response.json()["detail"] == "release_before_delivery", (
        "the operator must be told WHY, not just that it failed"
    )


@requires_real_db
def test_refunding_funded_money_without_a_dispute_is_a_conflict(api) -> None:  # noqa: ANN001
    """FR-D8 surfaced as an API contract: staff must dispute the deal first."""
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "l@example.com")

    _mark(client, headers, scene["payment_id"], "funded")
    response = _mark(client, headers, scene["payment_id"], "refunded")
    assert response.status_code == 409
    assert response.json()["detail"] == "deal_transition_blocked"

    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415

    with session() as db:
        assert db.get(EscrowPayment, scene["payment_id"]).status == EscrowStatus.funded


@requires_real_db
def test_an_unknown_target_status_is_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "m@example.com")
    assert _mark(client, headers, scene["payment_id"], "vanished").status_code == 422


@requires_real_db
def test_a_missing_payment_is_a_404(api) -> None:  # noqa: ANN001
    client, session = api
    _scene(session)
    headers = _staff_headers(session, "admin", "n@example.com")
    assert _mark(client, headers, 999999, "funded").status_code == 404


# ── provider holds (R6 / P7.b — T3.2) ─────────────────────────────────────────


def test_provider_events_route_is_registered() -> None:
    from app.api.admin_escrow import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/escrow/provider-events" in paths


def test_provider_events_is_declared_before_the_payment_detail_route() -> None:
    """`/escrow/{payment_id}` types the id as int, so a literal segment declared
    after it would 422 instead of matching. Order is the contract here."""
    from app.api.admin_escrow import router  # noqa: PLC0415

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    assert paths.index("/admin/escrow/provider-events") < paths.index("/admin/escrow/{payment_id}")


def _hold_a_refund(session, payment_id):  # noqa: ANN001, ANN202
    """Put the payment on the live rail, fund it, then have the bank say refunded."""
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with session() as db:
        payment = db.get(EscrowPayment, payment_id)
        payment.mode = "live"
        payment.provider_ref = "ESC-1"
        db.flush()
        escrow_service.apply_provider_event(
            db,
            escrow_service.record_provider_event(
                db, "generic", "op-1",
                {"event_id": "op-1", "escrow_ref": "ESC-1", "status": "funded"},
            ),
        )
        escrow_service.apply_provider_event(
            db,
            escrow_service.record_provider_event(
                db, "generic", "op-2",
                {"event_id": "op-2", "escrow_ref": "ESC-1", "status": "refunded"},
            ),
        )
        db.commit()


@requires_real_db
def test_an_analyst_may_read_the_provider_holds(api) -> None:  # noqa: ANN001
    """Watching the queue is analyst work; only marking money is admin-only."""
    client, session = api
    scene = _scene(session)
    _hold_a_refund(session, scene["payment_id"])
    headers = _staff_headers(session, "analyst", "ph1@example.com")

    response = client.get(f"{_A}/escrow/provider-events", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["reason"] == "needs_operator"
    assert items[0]["claimed_status"] == "refunded"
    assert items[0]["payment_status"] == "funded"
    assert items[0]["payment_id"] == scene["payment_id"]
    assert items[0]["deal_id"] == scene["deal_id"]


@requires_real_db
def test_the_provider_holds_need_authentication(api) -> None:  # noqa: ANN001
    client, _session = api
    assert client.get(f"{_A}/escrow/provider-events").status_code in {401, 403}


@requires_real_db
def test_the_escrow_counters_surface_the_number_of_holds(api) -> None:  # noqa: ANN001
    """An operator must see there is something to reconcile without opening a tab."""
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "analyst", "ph2@example.com")

    assert client.get(f"{_A}/escrow", headers=headers).json()["counters"]["provider_holds"] == 0
    _hold_a_refund(session, scene["payment_id"])
    assert client.get(f"{_A}/escrow", headers=headers).json()["counters"]["provider_holds"] == 1
