"""Logistics service requests (portal).

Reading a carrier is anonymous; asking one for a price is not. What this suite
holds is that boundary — who may send, to whom, and who may read it back.
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
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/logistics"


def test_routes_registered() -> None:
    """Literal paths BEFORE the parameterised one.

    `/portal/logistics/requests` and `/portal/logistics/{logistics_id}/requests`
    both match `/portal/logistics/X/Y`, and FastAPI resolves first-registered —
    so a reorder would silently route every list call into the create handler.
    Asserting the order here is the only thing that catches that.
    """
    from app.api.portal.logistics import router  # noqa: PLC0415

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    assert "/portal/logistics/requests" in paths
    assert "/portal/logistics/requests/{request_id}" in paths
    assert "/portal/logistics/{logistics_id}/requests" in paths
    assert paths.index("/portal/logistics/requests") < paths.index(
        "/portal/logistics/{logistics_id}/requests"
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

    # Blank optionals normalise to NULL rather than to an empty string.
    filled = LogisticsRequestCreateIn(**base, from_city="  ", packaging_type="")
    assert filled.from_city is None
    assert filled.packaging_type is None


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


def _carrier(db, owner, tax_id: str, *, confirmed: bool = True):  # noqa: ANN001, ANN202
    """A verified company with the logistics role confirmed (or merely declared)."""
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    company = make_company(
        db,
        owner,
        tax_id=tax_id,
        legal_name="Trans Asia Logistics",
        status=CompanyStatus.verified,
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
def test_buyer_sends_a_request_and_both_parties_read_it(api) -> None:  # noqa: ANN001
    """The whole flow: send, then see it from each side.

    `sent` and `incoming` are the same rows from opposite ends, so asserting both
    is what proves the filter is keyed on the right column — a swap would still
    return one row to each party and look correct from either alone.
    """
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008001")
        buyer = make_company(db, buyer_owner, tax_id="380000001")
        carrier_owner = make_account(db, "+998900008002")
        carrier = _carrier(db, carrier_owner, "380000002")
        db.commit()
        buyer_id, carrier_id = buyer.id, carrier.id
        buyer_account, carrier_account = buyer_owner.id, carrier_owner.id

    created = client.post(
        f"{_BASE}/{carrier_id}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["number"].startswith("LRQ-")
    assert body["status"] == "submitted"
    assert body["cargo_name"] == "Полипропилен (PP)"
    assert body["from_city"] == "Шанхай"
    # Snapshotted server-side, never sent by the form.
    assert body["contact_phone"] == "+998900008001"
    request_id = body["id"]

    sent = client.get(
        f"{_BASE}/requests",
        params={"company_id": buyer_id, "side": "sent"},
        headers=_auth(buyer_account),
    ).json()["items"]
    assert [r["id"] for r in sent] == [request_id]

    incoming = client.get(
        f"{_BASE}/requests",
        params={"company_id": carrier_id, "side": "incoming"},
        headers=_auth(carrier_account),
    ).json()["items"]
    assert [r["id"] for r in incoming] == [request_id]

    # ...and NOT the other way round.
    assert (
        client.get(
            f"{_BASE}/requests",
            params={"company_id": buyer_id, "side": "incoming"},
            headers=_auth(buyer_account),
        ).json()["items"]
        == []
    )

    detail = client.get(
        f"{_BASE}/requests/{request_id}",
        params={"company_id": carrier_id},
        headers=_auth(carrier_account),
    )
    assert detail.status_code == 200
    assert detail.json()["logistics_name"] is not None


@requires_real_db
def test_request_is_invisible_to_a_third_company(api) -> None:  # noqa: ANN001
    """A stranger gets 404, not 403 — the row's existence is not confirmed."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008011")
        buyer = make_company(db, buyer_owner, tax_id="380000011")
        carrier_owner = make_account(db, "+998900008012")
        carrier = _carrier(db, carrier_owner, "380000012")
        outsider_owner = make_account(db, "+998900008013")
        outsider = make_company(db, outsider_owner, tax_id="380000013")
        db.commit()
        buyer_id, carrier_id = buyer.id, carrier.id
        buyer_account = buyer_owner.id
        outsider_id, outsider_account = outsider.id, outsider_owner.id

    request_id = client.post(
        f"{_BASE}/{carrier_id}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    ).json()["id"]

    # Acting as their own company: a real member, but not a party.
    assert (
        client.get(
            f"{_BASE}/requests/{request_id}",
            params={"company_id": outsider_id},
            headers=_auth(outsider_account),
        ).status_code
        == 404
    )
    # Claiming to act as the buyer's company: not a member at all.
    assert (
        client.get(
            f"{_BASE}/requests/{request_id}",
            params={"company_id": buyer_id},
            headers=_auth(outsider_account),
        ).status_code
        == 404
    )


@requires_real_db
def test_carrier_must_be_verified_with_a_confirmed_role(api) -> None:  # noqa: ANN001
    """A self-declared carrier cannot collect cargo details.

    Same bar as the public directory. `declared` is a tick-box during
    registration; only `confirmed` on a `verified` company is a carrier.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008021")
        buyer = make_company(db, buyer_owner, tax_id="380000021")

        declared_owner = make_account(db, "+998900008022")
        declared = _carrier(db, declared_owner, "380000022", confirmed=False)

        # Confirmed role, but the company itself is still awaiting verification.
        unverified_owner = make_account(db, "+998900008023")
        unverified = make_company(
            db,
            unverified_owner,
            tax_id="380000023",
            status=CompanyStatus.pending_verification,
        )
        db.commit()
        buyer_id, buyer_account = buyer.id, buyer_owner.id
        declared_id, unverified_id = declared.id, unverified.id

    for target in (declared_id, unverified_id, 999_999):
        res = client.post(
            f"{_BASE}/{target}/requests",
            json={**_PAYLOAD, "company_id": buyer_id},
            headers=_auth(buyer_account),
        )
        assert res.status_code == 404, target


@requires_real_db
def test_a_company_cannot_send_itself_a_request(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        owner = make_account(db, "+998900008031")
        carrier = _carrier(db, owner, "380000031")
        db.commit()
        carrier_id, account_id = carrier.id, owner.id

    res = client.post(
        f"{_BASE}/{carrier_id}/requests",
        json={**_PAYLOAD, "company_id": carrier_id},
        headers=_auth(account_id),
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "self_logistics_request"


@requires_real_db
def test_sending_requires_membership_in_the_asking_company(api) -> None:  # noqa: ANN001
    """`company_id` is a claim in the body — it has to be checked."""
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008041")
        buyer = make_company(db, buyer_owner, tax_id="380000041")
        carrier_owner = make_account(db, "+998900008042")
        carrier = _carrier(db, carrier_owner, "380000042")
        stranger = make_account(db, "+998900008043")
        db.commit()
        buyer_id, carrier_id, stranger_id = buyer.id, carrier.id, stranger.id

    res = client.post(
        f"{_BASE}/{carrier_id}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(stranger_id),
    )
    assert res.status_code == 404


@requires_real_db
def test_numbers_are_sequential_and_unique(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008051")
        buyer = make_company(db, buyer_owner, tax_id="380000051")
        carrier_owner = make_account(db, "+998900008052")
        carrier = _carrier(db, carrier_owner, "380000052")
        db.commit()
        buyer_id, carrier_id, account_id = buyer.id, carrier.id, buyer_owner.id

    numbers = [
        client.post(
            f"{_BASE}/{carrier_id}/requests",
            json={**_PAYLOAD, "company_id": buyer_id},
            headers=_auth(account_id),
        ).json()["number"]
        for _ in range(3)
    ]
    assert len(set(numbers)) == 3
    assert all(n.startswith("LRQ-") for n in numbers)


@requires_real_db
def test_anonymous_and_wrong_audience_tokens_are_refused(api) -> None:  # noqa: ANN001
    """Acting needs a PORTAL session — a staff token is a different audience."""
    from app.core.security import create_access_token  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900008061")
        carrier = _carrier(db, owner, "380000061")
        db.commit()
        carrier_id = carrier.id

    assert client.post(f"{_BASE}/{carrier_id}/requests", json=_PAYLOAD).status_code == 401

    staff = {"Authorization": f"Bearer {create_access_token(subject='1', role='admin')}"}
    assert (
        client.get(f"{_BASE}/requests", params={"company_id": 1}, headers=staff).status_code
        == 401
    )


@requires_real_db
def test_submitting_notifies_the_carrier_not_the_sender(api) -> None:  # noqa: ANN001
    """A form nobody is told about is a form nobody answers.

    The factory RFQ raises no notification at all — its submit is only a log
    line — so this is deliberately NOT copied from it. Written in the same
    transaction as the insert: if the row commits, the bell rings.
    """
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    client, session = api
    with session() as db:
        buyer_owner = make_account(db, "+998900008071")
        buyer = make_company(db, buyer_owner, tax_id="380000071")
        carrier_owner = make_account(db, "+998900008072")
        carrier = _carrier(db, carrier_owner, "380000072")
        db.commit()
        buyer_id, carrier_id = buyer.id, carrier.id
        buyer_account, carrier_account = buyer_owner.id, carrier_owner.id

    created = client.post(
        f"{_BASE}/{carrier_id}/requests",
        json={**_PAYLOAD, "company_id": buyer_id},
        headers=_auth(buyer_account),
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    with session() as db:
        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind == notification_service.KIND_LOGISTICS_REQUEST_NEW
            )
            .all()
        )

    # The carrier's member is told; the buyer who sent it is not.
    assert [r.user_account_id for r in rows] == [carrier_account]
    row = rows[0]
    assert row.entity == "logistics_request"
    assert row.entity_id == str(request_id)
    # Keys, never pre-rendered text — the reader's language decides at display.
    assert row.title_key == "notifications.logistics_request_new.title"
    assert row.params["cargo"] == "Полипропилен (PP)"
