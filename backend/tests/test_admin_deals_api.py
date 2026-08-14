"""Staff deal oversight API tests (P2 W2 — T2.2).

Route registration is DB-free. Behaviour runs against test_polymer (guarded).

Staff see everything and touch almost nothing: the Trade Room is the parties'
record, so there is no staff write path into the chat at all. The one mutation
is dispute resolution, and it is admin-only — an analyst may read a dispute but
not decide it.
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
    from app.api.admin_deals import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/deals" in paths
    assert "/admin/deals/{deal_id}" in paths
    assert "/admin/deals/{deal_id}/messages" in paths
    assert "/admin/deals/{deal_id}/resolve-dispute" in paths


def test_no_staff_write_path_into_the_chat() -> None:
    """The room is the parties' record. Staff read it; they never post to it."""
    from app.api.admin_deals import router  # noqa: PLC0415

    for route in router.routes:  # type: ignore[attr-defined]
        if route.path.endswith("/messages"):
            assert route.methods == {"GET"}, f"{route.path} exposes {route.methods}"


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


def _scene(session, *, disputed: bool = False):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import CompanyStatus, DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

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
        deal_service.post_message(db, deal, buyer_acc, "Please confirm the lot number.")

        if disputed:
            for status_ in (
                DealStatus.contract_pending,
                DealStatus.contract_signed,
                DealStatus.payment_pending,
                DealStatus.paid_escrow,
            ):
                deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
            deal_service.transition_by_party(
                db, deal, buyer_acc, DealStatus.disputed, reason="nothing shipped"
            )
        db.commit()
        return {"deal_id": deal.id, "buyer_co": buyer.id, "seller_co": seller.id}


# ── read ──────────────────────────────────────────────────────────────────────


@requires_real_db
def test_analyst_lists_and_inspects(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "analyst", "analyst@example.com")

    listing = client.get(f"{_A}/deals", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == scene["deal_id"]

    detail = client.get(f"{_A}/deals/{scene['deal_id']}", headers=headers).json()
    assert detail["buyer_name"] is not None
    assert detail["seller_name"] is not None
    assert len(detail["timeline"]) >= 1
    assert detail["number"].startswith("DEAL-")


@requires_real_db
def test_staff_read_the_chat(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "analyst", "analyst@example.com")

    body = client.get(f"{_A}/deals/{scene['deal_id']}/messages", headers=headers).json()
    assert body["items"][0]["body"] == "Please confirm the lot number."


@requires_real_db
def test_filters_by_status_and_company(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "admin@example.com")

    assert (
        len(client.get(f"{_A}/deals?status=negotiation", headers=headers).json()["items"]) == 1
    )
    assert len(client.get(f"{_A}/deals?status=completed", headers=headers).json()["items"]) == 0
    by_company = client.get(
        f"{_A}/deals?company_id={scene['seller_co']}", headers=headers
    ).json()
    assert len(by_company["items"]) == 1


@requires_real_db
def test_search_by_deal_number(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)
    headers = _staff_headers(session, "admin", "admin@example.com")
    number = client.get(f"{_A}/deals/{scene['deal_id']}", headers=headers).json()["number"]

    found = client.get(f"{_A}/deals?q={number}", headers=headers).json()
    assert [d["id"] for d in found["items"]] == [scene["deal_id"]]


@requires_real_db
def test_portal_account_cannot_reach_the_admin_surface(api) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, session = api
    scene = _scene(session)
    with session() as db:
        account = make_account(db, "+998900000009")
        db.commit()
        token = create_portal_access_token(subject=str(account.id))

    response = client.get(
        f"{_A}/deals/{scene['deal_id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (401, 403)


# ── dispute resolution ────────────────────────────────────────────────────────


@requires_real_db
def test_admin_restores_a_disputed_deal(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session, disputed=True)
    headers = _staff_headers(session, "admin", "admin@example.com")

    resolved = client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "restore", "restore_to": "paid_escrow", "comment": "goods located"},
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "paid_escrow"


@requires_real_db
def test_admin_cancels_a_disputed_deal(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session, disputed=True)
    headers = _staff_headers(session, "admin", "admin@example.com")

    resolved = client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "cancel", "comment": "refunded off-platform"},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "cancelled"
    assert resolved.json()["cancelled_reason"] == "refunded off-platform"


@requires_real_db
def test_analyst_may_not_resolve_a_dispute(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session, disputed=True)
    headers = _staff_headers(session, "analyst", "analyst@example.com")

    response = client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "cancel", "comment": "no"},
        headers=headers,
    )
    assert response.status_code == 403


@requires_real_db
def test_cannot_resolve_a_deal_that_is_not_disputed(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _scene(session)  # still in negotiation
    headers = _staff_headers(session, "admin", "admin@example.com")

    response = client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "cancel", "comment": "nope"},
        headers=headers,
    )
    assert response.status_code == 409


@requires_real_db
def test_restore_to_an_impossible_status_is_rejected(api) -> None:  # noqa: ANN001
    """Staff resolve disputes; they do not get to teleport a deal to 'completed'."""
    client, session = api
    scene = _scene(session, disputed=True)
    headers = _staff_headers(session, "admin", "admin@example.com")

    response = client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "restore", "restore_to": "completed", "comment": "shortcut"},
        headers=headers,
    )
    assert response.status_code == 409


@requires_real_db
def test_resolution_is_recorded_in_the_timeline_and_audit(api) -> None:  # noqa: ANN001
    from app.models.staff import AuditLog  # noqa: PLC0415

    client, session = api
    scene = _scene(session, disputed=True)
    headers = _staff_headers(session, "admin", "admin@example.com")
    client.post(
        f"{_A}/deals/{scene['deal_id']}/resolve-dispute",
        json={"action": "restore", "restore_to": "shipped", "comment": "carrier confirmed"},
        headers=headers,
    )

    detail = client.get(f"{_A}/deals/{scene['deal_id']}", headers=headers).json()
    last = detail["timeline"][-1]
    assert last["to_status"] == "shipped"
    assert last["actor_kind"] == "staff"
    assert last["reason"] == "carrier confirmed"

    with session() as db:
        actions = {a.action for a in db.query(AuditLog).all()}
        assert "deal.resolve_dispute" in actions
