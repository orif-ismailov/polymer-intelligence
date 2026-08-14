"""Logistics requests: the broadcast pool and its per-carrier conversations.

A buyer states a job once and every verified carrier sees it. What this suite
holds is who that "every" is, and that a carrier's conversation is its own.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/logistics"


def test_routes_registered() -> None:
    """Literal paths BEFORE the parameterised ones.

    `/portal/logistics/pool` and `/portal/logistics/requests` would both be
    swallowed by a `/{something}` route declared first — FastAPI resolves
    first-registered — and the failure would be a silent misroute rather than an
    error. Asserting the ORDER is the only thing that catches that.
    """
    from app.api.portal.logistics import router  # noqa: PLC0415

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    for path in (
        "/portal/logistics/requests",
        "/portal/logistics/pool",
        "/portal/logistics/requests/{request_id}",
        "/portal/logistics/threads",
        "/portal/logistics/threads/{thread_id}/messages",
        "/portal/logistics/requests/{request_id}/threads",
    ):
        assert path in paths, path

    assert paths.index("/portal/logistics/requests") < paths.index(
        "/portal/logistics/requests/{request_id}"
    )
    assert paths.index("/portal/logistics/pool") < paths.index(
        "/portal/logistics/requests/{request_id}"
    )


def test_pool_payload_omits_the_buyer_contact() -> None:
    """A carrier gets the job, never the way to take it off-platform.

    `MarketRequestOut` makes the same call for polymer RFQs. The pool is a
    SEPARATE model rather than the buyer's minus a field, so that a field added
    to the buyer's payload cannot silently become visible to every carrier.
    """
    from app.schemas.portal_logistics import (  # noqa: PLC0415
        LogisticsPoolItemOut,
        LogisticsRequestOut,
    )

    assert "contact_phone" in LogisticsRequestOut.model_fields
    assert "contact_phone" not in LogisticsPoolItemOut.model_fields
    assert not (
        set(LogisticsPoolItemOut.model_fields)
        & {"contact_name", "contact_email", "phone", "email"}
    )


def test_create_payload_rejects_blank_and_nonpositive() -> None:
    """Bounds live on the schema, so a non-browser client cannot skip them."""
    import pydantic  # noqa: PLC0415

    from app.schemas.portal_logistics import LogisticsRequestCreateIn  # noqa: PLC0415

    base = {
        "company_id": 1,
        "cargo_name": "PP",
        "volume": "10",
        "from_country": "CN",
        "to_country": "UZ",
    }
    assert LogisticsRequestCreateIn(**base).volume_unit == "MT"

    for bad in ({"cargo_name": "   "}, {"volume": "0"}, {"volume": "-1"}, {"to_country": ""}):
        with pytest.raises(pydantic.ValidationError):
            LogisticsRequestCreateIn(**{**base, **bad})

    filled = LogisticsRequestCreateIn(**base, from_city="  ", packaging_type="")
    assert filled.from_city is None
    assert filled.packaging_type is None


def test_create_payload_has_no_carrier_field() -> None:
    """The broadcast is the model, not a default.

    Re-introducing a target field here is how this quietly becomes addressed
    again, with the pool still running beside it.
    """
    from app.schemas.portal_logistics import LogisticsRequestCreateIn  # noqa: PLC0415

    assert not (
        set(LogisticsRequestCreateIn.model_fields)
        & {"logistics_company_id", "carrier_company_id", "logistics_id"}
    )


# ── real-DB API fixture ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _carrier(db, owner, tax_id: str, name: str = "Trans Asia Logistics", *, confirmed: bool = True):  # noqa: ANN001, ANN202
    """A verified company with the logistics role confirmed (or merely declared)."""
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    company = make_company(
        db, owner, tax_id=tax_id, legal_name=name, status=CompanyStatus.verified
    )
    db.add(
        CompanyBusinessRole(
            company_id=company.id,
            role=Role.logistics_provider,
            status=BusinessRoleStatus.confirmed if confirmed else BusinessRoleStatus.declared,
        )
    )
    return company


_PAYLOAD = {
    "cargo_name": "Полипропилен (PP)",
    "volume": "500",
    "volume_unit": "MT",
    "packaging_type": "containers",
    "special_requirements": "Безопасная перевозка, ADR",
    "from_country": "CN",
    "from_city": "Шанхай",
    "to_country": "UZ",
    "to_city": "Ташкент",
}


@requires_real_db
def test_a_request_reaches_every_carrier_and_nobody_else(api) -> None:  # noqa: ANN001
    """The whole point of the change.

    Four viewers, one request: two confirmed carriers see it, a company that only
    DECLARED the role does not, and neither does the buyer who filed it — its own
    request is its own list, not a job it can bid on.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010001")
        buyer = make_company(db, buyer_owner, tax_id="400000001", legal_name="Shurtan GCC")

        c1_owner = make_account(db, "+998900010002")
        carrier1 = _carrier(db, c1_owner, "400000002", "Trans Asia")
        c2_owner = make_account(db, "+998900010003")
        carrier2 = _carrier(db, c2_owner, "400000003", "Uzbek Rail")

        # Declared, not confirmed — a tick-box during registration.
        d_owner = make_account(db, "+998900010004")
        declared = _carrier(db, d_owner, "400000004", "Says So", confirmed=False)

        # Verified, but never claimed the role at all.
        t_owner = make_account(db, "+998900010005")
        trader = make_company(
            db, t_owner, tax_id="400000005", status=CompanyStatus.verified
        )
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        c1, c1_account = carrier1.id, c1_owner.id
        c2, c2_account = carrier2.id, c2_owner.id
        d_id, d_account = declared.id, d_owner.id
        t_id, t_account = trader.id, t_owner.id

    created = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["number"].startswith("LRQ-")
    assert body["thread_count"] == 0
    request_id = body["id"]

    def pool(company_id: int, account_id: int) -> list[int]:
        res = client.get(
            f"{_BASE}/pool", params={"company_id": company_id}, headers=_auth(account_id)
        )
        assert res.status_code == 200
        return [i["id"] for i in res.json()["items"]]

    assert pool(c1, c1_account) == [request_id]
    assert pool(c2, c2_account) == [request_id]
    # Empty, not 403 — the page simply is not theirs.
    assert pool(d_id, d_account) == []
    assert pool(t_id, t_account) == []
    assert pool(buyer_id, buyer_account) == []

    # The buyer's own list is the other half of the split.
    own = client.get(
        f"{_BASE}/requests", params={"company_id": buyer_id}, headers=_auth(buyer_account)
    ).json()["items"]
    assert [r["id"] for r in own] == [request_id]


@requires_real_db
def test_visibility_guard_and_pool_query_agree(api) -> None:  # noqa: ANN001
    """The twin invariant, asserted directly.

    If `is_visible_to` and the pool list ever disagree, a carrier sees an
    «Ответить» button the API then refuses — or worse, the reverse. Checking the
    two against each other is the only way that stays true.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.models.logistics import LogisticsRequest  # noqa: PLC0415
    from app.services import logistics_service  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010011")
        buyer = make_company(db, buyer_owner, tax_id="400000011")
        c_owner = make_account(db, "+998900010012")
        carrier = _carrier(db, c_owner, "400000012")
        t_owner = make_account(db, "+998900010013")
        trader = make_company(
            db, t_owner, tax_id="400000013", status=CompanyStatus.verified
        )
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        carrier_id, trader_id = carrier.id, trader.id

    client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )

    with session() as db:
        from app.domains.companies.models import Company  # noqa: PLC0415

        request = db.query(LogisticsRequest).one()
        for company_id in (carrier_id, trader_id, buyer_id):
            company = db.get(Company, company_id)
            listed = request.id in {
                r.id
                for r in logistics_service.list_open_requests_for_carrier(db, company)
            }
            guarded = logistics_service.is_visible_to(db, request, company)
            assert listed == guarded, company_id


@requires_real_db
def test_each_carrier_gets_its_own_private_thread(api) -> None:  # noqa: ANN001
    """Per-carrier, not one room.

    A shared thread would show every carrier its competitors' terms, which is the
    single thing this shape exists to prevent — so it is asserted from both ends:
    each carrier reads its own, and neither can read the other's.
    """
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010021")
        buyer = make_company(db, buyer_owner, tax_id="400000021")
        c1_owner = make_account(db, "+998900010022")
        carrier1 = _carrier(db, c1_owner, "400000022", "Trans Asia")
        c2_owner = make_account(db, "+998900010023")
        carrier2 = _carrier(db, c2_owner, "400000023", "Uzbek Rail")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        c1, c1_account = carrier1.id, c1_owner.id
        c2, c2_account = carrier2.id, c2_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    t1 = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": c1},
        headers=_auth(c1_account),
    )
    assert t1.status_code == 201
    thread1 = t1.json()["id"]
    assert t1.json()["my_role"] == "carrier"

    # Idempotent: the chat screen calls this on every mount.
    again = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": c1},
        headers=_auth(c1_account),
    )
    assert again.json()["id"] == thread1

    thread2 = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": c2},
        headers=_auth(c2_account),
    ).json()["id"]
    assert thread2 != thread1

    client.post(
        f"{_BASE}/threads/{thread1}/messages",
        data={"company_id": c1, "body": "1450 USD за контейнер"},
        headers=_auth(c1_account),
    )

    # Carrier 2 cannot read carrier 1's room, and vice versa.
    assert (
        client.get(
            f"{_BASE}/threads/{thread1}/messages",
            params={"company_id": c2},
            headers=_auth(c2_account),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{_BASE}/threads/{thread2}/messages",
            params={"company_id": c1},
            headers=_auth(c1_account),
        ).status_code
        == 404
    )

    # The buyer reads both — they are the other party in each.
    for thread_id in (thread1, thread2):
        assert (
            client.get(
                f"{_BASE}/threads/{thread_id}/messages",
                params={"company_id": buyer_id},
                headers=_auth(buyer_account),
            ).status_code
            == 200
        )

    threads = client.get(
        f"{_BASE}/threads", params={"company_id": buyer_id}, headers=_auth(buyer_account)
    ).json()["items"]
    assert {t["id"] for t in threads} == {thread1, thread2}
    assert {t["my_role"] for t in threads} == {"buyer"}

    # And the buyer's own list now shows the broadcast landed.
    own = client.get(
        f"{_BASE}/requests", params={"company_id": buyer_id}, headers=_auth(buyer_account)
    ).json()["items"]
    assert own[0]["thread_count"] == 2


@requires_real_db
def test_pool_marks_the_carriers_own_thread(api) -> None:  # noqa: ANN001
    """`my_thread_id` is what turns «Ответить» into «Открыть чат»."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010031")
        buyer = make_company(db, buyer_owner, tax_id="400000031")
        c_owner = make_account(db, "+998900010032")
        carrier = _carrier(db, c_owner, "400000032")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        carrier_id, carrier_account = carrier.id, c_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    before = client.get(
        f"{_BASE}/pool", params={"company_id": carrier_id}, headers=_auth(carrier_account)
    ).json()["items"]
    assert before[0]["my_thread_id"] is None

    thread_id = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": carrier_id},
        headers=_auth(carrier_account),
    ).json()["id"]

    after = client.get(
        f"{_BASE}/pool", params={"company_id": carrier_id}, headers=_auth(carrier_account)
    ).json()["items"]
    assert after[0]["my_thread_id"] == thread_id


@requires_real_db
def test_a_non_carrier_cannot_open_a_thread(api) -> None:  # noqa: ANN001
    """404 covers "no such request", "not a carrier" and "your own request".

    One answer for all three: none of them is something the caller should be able
    to tell apart by probing.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010041")
        buyer = make_company(db, buyer_owner, tax_id="400000041")
        t_owner = make_account(db, "+998900010042")
        trader = make_company(
            db, t_owner, tax_id="400000042", status=CompanyStatus.verified
        )
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        trader_id, trader_account = trader.id, t_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    # Not a carrier.
    assert (
        client.post(
            f"{_BASE}/requests/{request_id}/threads",
            json={"company_id": trader_id},
            headers=_auth(trader_account),
        ).status_code
        == 404
    )
    # The buyer bidding on itself.
    assert (
        client.post(
            f"{_BASE}/requests/{request_id}/threads",
            json={"company_id": buyer_id},
            headers=_auth(buyer_account),
        ).status_code
        == 404
    )


@requires_real_db
def test_messages_reject_an_empty_body(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010051")
        buyer = make_company(db, buyer_owner, tax_id="400000051")
        c_owner = make_account(db, "+998900010052")
        carrier = _carrier(db, c_owner, "400000052")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        carrier_id, carrier_account = carrier.id, c_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]
    thread_id = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": carrier_id},
        headers=_auth(carrier_account),
    ).json()["id"]

    res = client.post(
        f"{_BASE}/threads/{thread_id}/messages",
        data={"company_id": carrier_id, "body": "   "},
        headers=_auth(carrier_account),
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "empty_message"


@requires_real_db
def test_broadcast_notifies_every_carrier_but_not_the_buyer(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010061")
        buyer = make_company(db, buyer_owner, tax_id="400000061")
        c1_owner = make_account(db, "+998900010062")
        _carrier(db, c1_owner, "400000062", "Trans Asia")
        c2_owner = make_account(db, "+998900010063")
        _carrier(db, c2_owner, "400000063", "Uzbek Rail")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        recipients = {c1_owner.id, c2_owner.id}

    client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )

    with session() as db:
        from app.models.notifications import PortalNotification  # noqa: PLC0415
        from app.services import notification_service  # noqa: PLC0415

        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind
                == notification_service.KIND_LOGISTICS_REQUEST_NEW
            )
            .all()
        )

    assert {r.user_account_id for r in rows} == recipients
    assert all(r.entity == "logistics_request" for r in rows)


@requires_real_db
def test_anonymous_and_wrong_audience_tokens_are_refused(api) -> None:  # noqa: ANN001
    """Acting needs a PORTAL session — a staff token is a different audience."""
    from app.core.security import create_access_token  # noqa: PLC0415

    client, _session = api

    assert client.get(f"{_BASE}/pool", params={"company_id": 1}).status_code == 401
    staff = {"Authorization": f"Bearer {create_access_token(subject='1', role='admin')}"}
    assert (
        client.get(f"{_BASE}/pool", params={"company_id": 1}, headers=staff).status_code
        == 401
    )


# ── admin oversight (admin_logistics_requests.py) ───────────────────────────────

_ADMIN_BASE = "/api/v1/admin/logistics-requests"


def _staff_auth(session, role: str, email: str) -> dict[str, str]:  # noqa: ANN001
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.enums import StaffRole  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.role = StaffRole(role)
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"}


def test_admin_routes_registered() -> None:
    from app.api.admin_logistics_requests import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/logistics-requests" in paths
    assert "/admin/logistics-requests/{request_id}" in paths


@requires_real_db
def test_admin_authz(api) -> None:  # noqa: ANN001
    client, session = api
    assert client.get(_ADMIN_BASE).status_code == 401
    viewer = _staff_auth(session, "viewer", "log-viewer@x.com")
    assert client.get(_ADMIN_BASE, headers=viewer).status_code == 403
    trader = _staff_auth(session, "trader", "log-trader@x.com")
    assert client.get(_ADMIN_BASE, headers=trader).status_code == 403
    analyst = _staff_auth(session, "analyst", "log-analyst@x.com")
    assert client.get(_ADMIN_BASE, headers=analyst).status_code == 200
    admin = _staff_auth(session, "admin", "log-admin@x.com")
    assert client.get(_ADMIN_BASE, headers=admin).status_code == 200


@requires_real_db
def test_admin_sees_every_carrier_thread(api) -> None:  # noqa: ANN001
    """The whole board, not one carrier's scoped view.

    A single carrier's portal view (test_each_carrier_gets_its_own_private_thread
    above) only ever sees its own thread — that is the point of the shape. Staff
    oversight is the other half: the admin detail endpoint must show every
    carrier's thread on the request, not just one.
    """
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900010031")
        buyer = make_company(db, buyer_owner, tax_id="400000031")
        c1_owner = make_account(db, "+998900010032")
        carrier1 = _carrier(db, c1_owner, "400000032", "Trans Asia")
        c2_owner = make_account(db, "+998900010033")
        carrier2 = _carrier(db, c2_owner, "400000033", "Uzbek Rail")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        c1, c1_account = carrier1.id, c1_owner.id
        c2, c2_account = carrier2.id, c2_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": c1},
        headers=_auth(c1_account),
    )
    client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": c2},
        headers=_auth(c2_account),
    )

    analyst = _staff_auth(session, "analyst", "log-board@x.com")
    resp = client.get(f"{_ADMIN_BASE}/{request_id}", headers=analyst)
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread_count"] == 2
    carrier_ids = {t["carrier_company_id"] for t in body["threads"]}
    assert carrier_ids == {c1, c2}


@requires_real_db
def test_admin_list_bad_status_and_unknown_id(api) -> None:  # noqa: ANN001
    client, session = api
    analyst = _staff_auth(session, "analyst", "log-errors@x.com")
    assert (
        client.get(_ADMIN_BASE, params={"status": "bogus"}, headers=analyst).status_code
        == 422
    )
    assert client.get(f"{_ADMIN_BASE}/999999999", headers=analyst).status_code == 404
