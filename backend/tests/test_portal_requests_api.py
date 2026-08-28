"""Portal purchase-request API tests (R2 W3 T3.3).

Route reg DB-free; the rest against test_polymer (guarded): create a request
(portal-origin, appears like a TG one), list/detail, cancel from a client-visible
non-terminal state, and cross-company isolation. REQUEST_NOTIFY_CHAT_ID unset →
group-notify no-ops.
"""

from __future__ import annotations

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

_BASE = "/api/v1/portal/requests"

_WIZARD = {
    "product_text": "HDPE film grade",
    "grade_text": "F0348",
    "polymer_type": "HDPE",
    "volume": "50.000",
    "volume_unit": "MT",
    "urgency": "high",
}


def test_request_routes_registered() -> None:
    from app.domains.requests.api_portal import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/requests" in paths
    assert "/portal/requests/{request_id}" in paths
    assert "/portal/requests/{request_id}/files" in paths
    assert "/portal/requests/{request_id}/cancel" in paths


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

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


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _setup_company(session):  # noqa: ANN001, ANN202
    with session() as db:
        owner = make_account(db, "+998900006001")
        company = make_company(db, owner, tax_id="316000001")
        db.commit()
        return owner.id, company.id


@requires_real_db
def test_create_and_detail(api) -> None:  # noqa: ANN001
    client, session = api
    owner_id, company_id = _setup_company(session)

    resp = client.post(
        _BASE, json={"company_id": company_id, **_WIZARD}, headers=_auth(owner_id)
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["id"]
    assert resp.json()["status"] == "new"

    # appears in the dashboard exactly like a TG request (company_id set, client NULL)
    with session() as db:
        from app.domains.requests.models import Request  # noqa: PLC0415
        row = db.get(Request, rid)
        assert row.company_id == company_id
        assert row.client_id is None

    detail = client.get(
        f"{_BASE}/{rid}", params={"company_id": company_id}, headers=_auth(owner_id)
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["number"].startswith("REQ-")
    assert len(body["history"]) == 1
    assert body["history"][0]["to_status"] == "new"


@requires_real_db
def test_list_and_cancel(api) -> None:  # noqa: ANN001
    client, session = api
    owner_id, company_id = _setup_company(session)
    rid = client.post(
        _BASE, json={"company_id": company_id, **_WIZARD}, headers=_auth(owner_id)
    ).json()["id"]

    listing = client.get(_BASE, params={"company_id": company_id}, headers=_auth(owner_id))
    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()] == [rid]

    # cancel from `new` (client-visible non-terminal) is allowed
    cancel = client.post(
        f"{_BASE}/{rid}/cancel", params={"company_id": company_id}, headers=_auth(owner_id)
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


@requires_real_db
def test_visibility_and_docs_reach_the_row_and_the_supplier(api) -> None:  # noqa: ANN001
    """The tender sheet's two answers are stored and acted on — not decorated.

    Both used to be folded into the free-text `comment`, so «все поставщики»
    changed nothing (the column kept its `verified_only` default) and the doc
    checklist never reached the card a supplier reads.
    """
    from app.domains.deals import rfq as rfq_service  # noqa: PLC0415
    from app.domains.requests.models import Request  # noqa: PLC0415
    from app.models.enums import CompanyStatus, RfqVisibility  # noqa: PLC0415

    client, session = api
    owner_id, company_id = _setup_company(session)

    open_to_all = client.post(
        _BASE,
        json={
            "company_id": company_id,
            **_WIZARD,
            "visibility": "all",
            # `coo` is the wizard's name; `origin_cert` is the code — and an
            # unknown one is dropped rather than stored.
            "required_docs": ["origin_cert", "sds", "nonsense"],
        },
        headers=_auth(owner_id),
    )
    assert open_to_all.status_code == 201, open_to_all.text
    open_id = open_to_all.json()["id"]

    verified_only_id = client.post(
        _BASE, json={"company_id": company_id, **_WIZARD}, headers=_auth(owner_id)
    ).json()["id"]

    with session() as db:
        row = db.get(Request, open_id)
        assert row.visibility == RfqVisibility.all
        assert row.required_docs == ["origin_cert", "sds"]
        # The default is the safe one: a tender is verified-only unless asked.
        assert db.get(Request, verified_only_id).visibility == RfqVisibility.verified_only

    # The buyer reads back what they set (a screen that can write a field and
    # not see it is how the value silently disappears on the next save).
    detail = client.get(
        f"{_BASE}/{open_id}", params={"company_id": company_id}, headers=_auth(owner_id)
    ).json()
    assert detail["visibility"] == "all"
    assert detail["required_docs"] == ["origin_cert", "sds"]

    # And the promise holds where it is enforced: an UNVERIFIED supplier sees
    # the open tender and not the verified-only one.
    with session() as db:
        supplier_owner = make_account(db, "+998900006010")
        supplier = make_company(
            db, supplier_owner, tax_id="316000010", roles=["distributor"]
        )
        assert supplier.status != CompanyStatus.verified
        db.commit()
        visible = {r.id for r in rfq_service.list_open_requests(db, supplier)}
        assert open_id in visible
        assert verified_only_id not in visible


@requires_real_db
def test_selected_visibility_is_refused(api) -> None:  # noqa: ANN001
    """`selected` needs a supplier list this body cannot carry, and an empty one
    would publish a tender nobody can answer — so it is a 422, not a default."""
    client, session = api
    owner_id, company_id = _setup_company(session)

    resp = client.post(
        _BASE,
        json={"company_id": company_id, **_WIZARD, "visibility": "selected"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 422, resp.text


@requires_real_db
def test_cross_company_isolation(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        a_owner = make_account(db, "+998900006100")
        make_company(db, a_owner, tax_id="316000100")
        b_owner = make_account(db, "+998900006101")
        company_b = make_company(db, b_owner, tax_id="316000101")
        db.commit()
        a_owner_id, company_b_id = a_owner.id, company_b.id

    # A acting, claims B → 404
    resp = client.get(_BASE, params={"company_id": company_b_id}, headers=_auth(a_owner_id))
    assert resp.status_code == 404


@requires_real_db
def test_request_daily_rate_limit(api) -> None:  # noqa: ANN001
    """The 11th request in a day for a company is rejected with 429 (R2 W6 T6.1)."""
    client, session = api
    owner_id, company_id = _setup_company(session)
    body = {"company_id": company_id, **_WIZARD}
    for _ in range(10):
        assert client.post(_BASE, json=body, headers=_auth(owner_id)).status_code == 201
    over = client.post(_BASE, json=body, headers=_auth(owner_id))
    assert over.status_code == 429
