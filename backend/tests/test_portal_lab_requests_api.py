"""Laboratory requests: the broadcast pool and its per-laboratory conversations.

The same shape as `test_portal_logistics_api`, one domain over: a buyer says what
needs testing once, every verified laboratory sees it, and each interested lab
gets a room of its own.

What this suite additionally holds is the boundary with **P6**. `lab_orders` is a
different flow with a different owner — staff run it, it hangs off an offer or a
deal, and it is the only thing that can set the gold «Laboratory Verified» badge.
Two things called "lab" in one codebase drift into each other unless something
says they must not.
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

_BASE = "/api/v1/portal/lab"


def test_routes_registered() -> None:
    """Literal paths BEFORE the parameterised ones.

    `/portal/lab/pool` and `/portal/lab/requests` would both be swallowed by a
    `/{something}` route declared first — FastAPI resolves first-registered — and
    the failure would be a silent misroute rather than an error.
    """
    from app.api.portal.lab_requests import router  # noqa: PLC0415

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    for path in (
        "/portal/lab/requests",
        "/portal/lab/pool",
        "/portal/lab/requests/{request_id}",
        "/portal/lab/threads",
        "/portal/lab/threads/{thread_id}/messages",
        "/portal/lab/requests/{request_id}/threads",
    ):
        assert path in paths, path

    assert paths.index("/portal/lab/requests") < paths.index(
        "/portal/lab/requests/{request_id}"
    )
    assert paths.index("/portal/lab/pool") < paths.index(
        "/portal/lab/requests/{request_id}"
    )


def test_prefix_does_not_collide_with_the_p6_lab_order_family() -> None:
    """`/portal/lab/...` and `/portal/companies/{id}/lab-orders` are separate flows.

    Both are "lab" to a reader and neither is the other: P6 is staff-run analysis
    against an offer, this is a client↔laboratory channel. The prefixes must not
    converge, and the P6 routes must still be mounted after this one was added.
    """
    from app.api.portal import lab, lab_requests  # noqa: PLC0415

    p6 = {r.path for r in lab.router.routes}  # type: ignore[attr-defined]
    new = {r.path for r in lab_requests.router.routes}  # type: ignore[attr-defined]

    # P6 still mounted, and still where it was.
    assert "/portal/companies/{company_id}/lab-orders" in p6
    assert lab_requests.router.prefix == "/portal/lab"
    # Neither family may reach into the other's namespace.
    assert not (p6 & new)
    assert not any(p.startswith("/portal/lab/") for p in p6)
    assert not any("lab-orders" in p for p in new)


def test_lab_verified_is_still_reachable_only_through_p6() -> None:
    """The gold badge is P6's to set, and this work must not have widened that.

    `lab_service.complete_with_result` is the single writer. If a second one
    appears, «мы это проанализировали» stops meaning what the market filter says
    it means.
    """
    import pathlib  # noqa: PLC0415
    import re  # noqa: PLC0415

    # Assignment to the ORM attribute, not `==` and not a filter kwarg — those
    # are reads, and every market surface has one.
    assign = re.compile(r"\.lab_verified\s*=(?!=)")
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    writers = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if assign.search(path.read_text(encoding="utf-8"))
    }
    assert writers == {"services/lab_service.py"}, writers


def test_pool_payload_omits_the_buyer_contact() -> None:
    """A laboratory gets the job, never the way to take it off-platform.

    The contact block is the one part of this form the mockup asks for
    explicitly, which makes it exactly the part that must not broadcast. A
    SEPARATE model rather than the buyer's minus three fields, so a field added
    upstream cannot silently become visible to every laboratory.
    """
    from app.schemas.portal_laboratory import (  # noqa: PLC0415
        LabPoolItemOut,
        LabRequestOut,
    )

    for field in ("contact_name", "contact_email", "contact_phone"):
        assert field in LabRequestOut.model_fields, field
    assert not (
        set(LabPoolItemOut.model_fields)
        & {"contact_name", "contact_email", "contact_phone", "phone", "email"}
    )


def test_create_payload_bounds_and_trims() -> None:
    """Bounds live on the schema, so a non-browser client cannot skip them."""
    import pydantic  # noqa: PLC0415

    from app.schemas.portal_laboratory import LabRequestCreateIn  # noqa: PLC0415

    base = {"company_id": 1, "product_text": "HDPE S5502 BN"}
    assert LabRequestCreateIn(**base).methods == []
    assert LabRequestCreateIn(**base).is_urgent is False

    for bad in ({"product_text": "   "}, {"product_text": ""}, {"methods": ["x"] * 49}):
        with pytest.raises(pydantic.ValidationError):
            LabRequestCreateIn(**{**base, **bad})

    filled = LabRequestCreateIn(
        **base,
        grade_text="  ",
        sample_qty="",
        methods=["mfi", "  ", "density"],
    )
    assert filled.grade_text is None
    assert filled.sample_qty is None
    assert filled.methods == ["mfi", "density"]


def test_create_payload_has_no_laboratory_field() -> None:
    """The broadcast is the model, not a default.

    The mockup's «Выбранная лаборатория» was dropped deliberately. Re-introducing
    a target field is how this quietly becomes addressed again, with the pool
    still running beside it.
    """
    from app.schemas.portal_laboratory import LabRequestCreateIn  # noqa: PLC0415

    assert not (
        set(LabRequestCreateIn.model_fields)
        & {"laboratory_company_id", "lab_company_id", "laboratory_id", "lab_id"}
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


def _lab(db, owner, tax_id: str, name: str = "Central Polymer Lab", *, confirmed: bool = True):  # noqa: ANN001, ANN202
    """A verified company with the laboratory role confirmed (or merely declared)."""
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    company = make_company(
        db, owner, tax_id=tax_id, legal_name=name, status=CompanyStatus.verified
    )
    db.add(
        CompanyBusinessRole(
            company_id=company.id,
            role=Role.laboratory,
            status=BusinessRoleStatus.confirmed if confirmed else BusinessRoleStatus.declared,
        )
    )
    return company


_PAYLOAD = {
    "product_text": "HDPE S5502 BN",
    "grade_text": "S5502",
    "study_type": "full_passport",
    "methods": ["mfi", "density", "tensile_strength"],
    "sample_qty": "1 кг",
    "comment": "Нужен полный паспорт",
    "purpose": "quality_and_compatibility",
    "is_urgent": True,
    "contact_name": "Азиз Каримов",
    "contact_email": "aziz@example.uz",
    "contact_phone": "+998901112233",
}


@requires_real_db
def test_a_request_reaches_every_lab_and_nobody_else(api) -> None:  # noqa: ANN001
    """Five viewers, one request.

    Two confirmed laboratories see it; a company that only DECLARED the role does
    not; a verified trader does not; and neither does the buyer who filed it —
    its own request is its own list, not a job it can bid on.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020001")
        buyer = make_company(db, buyer_owner, tax_id="410000001", legal_name="Shurtan GCC")

        l1_owner = make_account(db, "+998900020002")
        lab1 = _lab(db, l1_owner, "410000002", "Central Polymer Lab")
        l2_owner = make_account(db, "+998900020003")
        lab2 = _lab(db, l2_owner, "410000003", "PolyTest Lab")

        # Declared, not confirmed — a tick-box during registration.
        d_owner = make_account(db, "+998900020004")
        declared = _lab(db, d_owner, "410000004", "Says So", confirmed=False)

        # Verified, but never claimed the role at all.
        t_owner = make_account(db, "+998900020005")
        trader = make_company(db, t_owner, tax_id="410000005", status=CompanyStatus.verified)
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        l1, l1_account = lab1.id, l1_owner.id
        l2, l2_account = lab2.id, l2_owner.id
        d_id, d_account = declared.id, d_owner.id
        t_id, t_account = trader.id, t_owner.id

    created = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )
    assert created.status_code == 201
    body = created.json()
    # LBR-, not LAB- — `lab_service.generate_lab_number` already owns that prefix
    # and two flows sharing a number format is a support trap.
    assert body["number"].startswith("LBR-")
    assert body["thread_count"] == 0
    assert body["methods"] == ["mfi", "density", "tensile_strength"]
    assert body["is_urgent"] is True
    request_id = body["id"]

    def pool(company_id: int, account_id: int) -> list[int]:
        res = client.get(
            f"{_BASE}/pool", params={"company_id": company_id}, headers=_auth(account_id)
        )
        assert res.status_code == 200
        return [i["id"] for i in res.json()["items"]]

    assert pool(l1, l1_account) == [request_id]
    assert pool(l2, l2_account) == [request_id]
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
def test_the_pool_never_carries_the_buyers_contact_over_the_wire(api) -> None:  # noqa: ANN001
    """The schema guard, proved end to end against a request that HAS a contact."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020091")
        buyer = make_company(db, buyer_owner, tax_id="410000091")
        l_owner = make_account(db, "+998900020092")
        lab = _lab(db, l_owner, "410000092")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        lab_id, lab_account = lab.id, l_owner.id

    mine = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()
    assert mine["contact_phone"] == "+998901112233"
    assert mine["contact_email"] == "aziz@example.uz"

    item = client.get(
        f"{_BASE}/pool", params={"company_id": lab_id}, headers=_auth(lab_account)
    ).json()["items"][0]
    payload = repr(item)
    assert "+998901112233" not in payload
    assert "aziz@example.uz" not in payload
    assert "Азиз" not in payload


@requires_real_db
def test_visibility_guard_and_pool_query_agree(api) -> None:  # noqa: ANN001
    """The twin invariant, asserted directly.

    If `is_visible_to` and the pool list ever disagree, a laboratory sees an
    «Ответить» button the API then refuses — or worse, the reverse.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.models.laboratory import LabRequest  # noqa: PLC0415
    from app.services import laboratory_service  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020011")
        buyer = make_company(db, buyer_owner, tax_id="410000011")
        l_owner = make_account(db, "+998900020012")
        lab = _lab(db, l_owner, "410000012")
        d_owner = make_account(db, "+998900020014")
        declared = _lab(db, d_owner, "410000014", "Says So", confirmed=False)
        t_owner = make_account(db, "+998900020013")
        trader = make_company(db, t_owner, tax_id="410000013", status=CompanyStatus.verified)
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        lab_id, trader_id, declared_id = lab.id, trader.id, declared.id

    client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )

    with session() as db:
        from app.models.companies import Company  # noqa: PLC0415

        request = db.query(LabRequest).one()
        for company_id in (lab_id, trader_id, declared_id, buyer_id):
            company = db.get(Company, company_id)
            listed = request.id in {
                r.id for r in laboratory_service.list_open_requests_for_lab(db, company)
            }
            guarded = laboratory_service.is_visible_to(db, request, company)
            assert listed == guarded, company_id


@requires_real_db
def test_each_lab_gets_its_own_private_thread(api) -> None:  # noqa: ANN001
    """Per-laboratory, not one room.

    A shared thread would show every laboratory its competitors' quoted price and
    turnaround, which is the single thing this shape exists to prevent — so it is
    asserted from both ends.
    """
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020021")
        buyer = make_company(db, buyer_owner, tax_id="410000021")
        l1_owner = make_account(db, "+998900020022")
        lab1 = _lab(db, l1_owner, "410000022", "Central Polymer Lab")
        l2_owner = make_account(db, "+998900020023")
        lab2 = _lab(db, l2_owner, "410000023", "PolyTest Lab")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        l1, l1_account = lab1.id, l1_owner.id
        l2, l2_account = lab2.id, l2_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    t1 = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": l1},
        headers=_auth(l1_account),
    )
    assert t1.status_code == 201
    thread1 = t1.json()["id"]
    assert t1.json()["my_role"] == "laboratory"

    # Idempotent: the chat screen calls this on every mount.
    again = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": l1},
        headers=_auth(l1_account),
    )
    assert again.json()["id"] == thread1

    thread2 = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": l2},
        headers=_auth(l2_account),
    ).json()["id"]
    assert thread2 != thread1

    client.post(
        f"{_BASE}/threads/{thread1}/messages",
        data={"company_id": l1, "body": "ПТР + плотность — 2 дня, 1 200 000 сум"},
        headers=_auth(l1_account),
    )

    # Laboratory 2 cannot read laboratory 1's room, and vice versa.
    assert (
        client.get(
            f"{_BASE}/threads/{thread1}/messages",
            params={"company_id": l2},
            headers=_auth(l2_account),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{_BASE}/threads/{thread2}/messages",
            params={"company_id": l1},
            headers=_auth(l1_account),
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
    assert {t["counterparty_name"] for t in threads} == {
        "Central Polymer Lab",
        "PolyTest Lab",
    }

    # And the buyer's own list now shows the broadcast landed.
    own = client.get(
        f"{_BASE}/requests", params={"company_id": buyer_id}, headers=_auth(buyer_account)
    ).json()["items"]
    assert own[0]["thread_count"] == 2


@requires_real_db
def test_pool_marks_the_labs_own_thread(api) -> None:  # noqa: ANN001
    """`my_thread_id` is what turns «Ответить» into «Открыть чат»."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020031")
        buyer = make_company(db, buyer_owner, tax_id="410000031")
        l_owner = make_account(db, "+998900020032")
        lab = _lab(db, l_owner, "410000032")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        lab_id, lab_account = lab.id, l_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    before = client.get(
        f"{_BASE}/pool", params={"company_id": lab_id}, headers=_auth(lab_account)
    ).json()["items"]
    assert before[0]["my_thread_id"] is None

    thread_id = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": lab_id},
        headers=_auth(lab_account),
    ).json()["id"]

    after = client.get(
        f"{_BASE}/pool", params={"company_id": lab_id}, headers=_auth(lab_account)
    ).json()["items"]
    assert after[0]["my_thread_id"] == thread_id


@requires_real_db
def test_a_non_lab_cannot_open_a_thread(api) -> None:  # noqa: ANN001
    """404 covers "no such request", "not a laboratory" and "your own request".

    One answer for all three: none of them is something the caller should be able
    to tell apart by probing.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020041")
        buyer = make_company(db, buyer_owner, tax_id="410000041")
        t_owner = make_account(db, "+998900020042")
        trader = make_company(db, t_owner, tax_id="410000042", status=CompanyStatus.verified)
        d_owner = make_account(db, "+998900020043")
        declared = _lab(db, d_owner, "410000043", "Says So", confirmed=False)
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        trader_id, trader_account = trader.id, t_owner.id
        declared_id, declared_account = declared.id, d_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    # Not a laboratory at all.
    assert (
        client.post(
            f"{_BASE}/requests/{request_id}/threads",
            json={"company_id": trader_id},
            headers=_auth(trader_account),
        ).status_code
        == 404
    )
    # Declared the role but was never confirmed in it.
    assert (
        client.post(
            f"{_BASE}/requests/{request_id}/threads",
            json={"company_id": declared_id},
            headers=_auth(declared_account),
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
        buyer_owner = make_account(db, "+998900020051")
        buyer = make_company(db, buyer_owner, tax_id="410000051")
        l_owner = make_account(db, "+998900020052")
        lab = _lab(db, l_owner, "410000052")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        lab_id, lab_account = lab.id, l_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]
    thread_id = client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": lab_id},
        headers=_auth(lab_account),
    ).json()["id"]

    res = client.post(
        f"{_BASE}/threads/{thread_id}/messages",
        data={"company_id": lab_id, "body": "   "},
        headers=_auth(lab_account),
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "empty_message"


@requires_real_db
def test_broadcast_notifies_every_lab_but_not_the_buyer(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020061")
        buyer = make_company(db, buyer_owner, tax_id="410000061")
        l1_owner = make_account(db, "+998900020062")
        _lab(db, l1_owner, "410000062", "Central Polymer Lab")
        l2_owner = make_account(db, "+998900020063")
        _lab(db, l2_owner, "410000063", "PolyTest Lab")
        # Declared-only: sees nothing, so is told nothing.
        d_owner = make_account(db, "+998900020064")
        _lab(db, d_owner, "410000064", "Says So", confirmed=False)
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        recipients = {l1_owner.id, l2_owner.id}

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
            .filter(PortalNotification.kind == notification_service.KIND_LAB_REQUEST_NEW)
            .all()
        )

    assert {r.user_account_id for r in rows} == recipients
    assert all(r.entity == "lab_request" for r in rows)


@requires_real_db
def test_contact_phone_falls_back_to_the_account(api) -> None:  # noqa: ANN001
    """The mockup asks for a phone, but leaving it blank must not lose the buyer.

    Collected, not snapshotted — `user_accounts` has no email column and a
    nullable name, so the phone is the one field there is something to fall back
    ON.
    """
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020071")
        buyer = make_company(db, buyer_owner, tax_id="410000071")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id

    body = client.post(
        f"{_BASE}/requests",
        json={"company_id": buyer_id, "product_text": "LDPE 15803-020"},
        headers=_auth(buyer_account),
    ).json()

    assert body["contact_phone"] == "+998900020071"
    assert body["contact_email"] is None


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


# ── admin oversight (admin_lab_requests.py) ─────────────────────────────────────

_ADMIN_BASE = "/api/v1/admin/lab-requests"


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
    from app.api.admin_lab_requests import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/lab-requests" in paths
    assert "/admin/lab-requests/{request_id}" in paths


@requires_real_db
def test_admin_authz(api) -> None:  # noqa: ANN001
    client, session = api
    assert client.get(_ADMIN_BASE).status_code == 401
    viewer = _staff_auth(session, "viewer", "lab-viewer@x.com")
    assert client.get(_ADMIN_BASE, headers=viewer).status_code == 403
    trader = _staff_auth(session, "trader", "lab-trader@x.com")
    assert client.get(_ADMIN_BASE, headers=trader).status_code == 403
    analyst = _staff_auth(session, "analyst", "lab-analyst@x.com")
    assert client.get(_ADMIN_BASE, headers=analyst).status_code == 200
    admin = _staff_auth(session, "admin", "lab-admin@x.com")
    assert client.get(_ADMIN_BASE, headers=admin).status_code == 200


@requires_real_db
def test_admin_sees_every_laboratory_thread(api) -> None:  # noqa: ANN001
    """The whole board, not one laboratory's scoped view — the admin twin of
    test_each_lab_gets_its_own_private_thread above."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900020041")
        buyer = make_company(db, buyer_owner, tax_id="410000041")
        l1_owner = make_account(db, "+998900020042")
        lab1 = _lab(db, l1_owner, "410000042", "Central Polymer Lab")
        l2_owner = make_account(db, "+998900020043")
        lab2 = _lab(db, l2_owner, "410000043", "PolyTest Lab")
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        l1, l1_account = lab1.id, l1_owner.id
        l2, l2_account = lab2.id, l2_owner.id

    request_id = client.post(
        f"{_BASE}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": l1},
        headers=_auth(l1_account),
    )
    client.post(
        f"{_BASE}/requests/{request_id}/threads",
        json={"company_id": l2},
        headers=_auth(l2_account),
    )

    analyst = _staff_auth(session, "analyst", "lab-board@x.com")
    resp = client.get(f"{_ADMIN_BASE}/{request_id}", headers=analyst)
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread_count"] == 2
    lab_ids = {t["laboratory_company_id"] for t in body["threads"]}
    assert lab_ids == {l1, l2}


@requires_real_db
def test_admin_list_bad_status_and_unknown_id(api) -> None:  # noqa: ANN001
    client, session = api
    analyst = _staff_auth(session, "analyst", "lab-errors@x.com")
    assert (
        client.get(_ADMIN_BASE, params={"status": "bogus"}, headers=analyst).status_code
        == 422
    )
    assert client.get(f"{_ADMIN_BASE}/999999999", headers=analyst).status_code == 404
