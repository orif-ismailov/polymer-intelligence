"""Portal manufacturers directory + factory RFQ + chat (migration 0034)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/manufacturers"


def test_manufacturer_routes_registered() -> None:
    from app.api.portal.manufacturers import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/manufacturers" in paths
    assert "/portal/manufacturers/{manufacturer_id}/rfqs" in paths
    assert "/portal/manufacturers/{manufacturer_id}/threads" in paths
    assert "/portal/manufacturers/rfqs/{rfq_id}" in paths
    assert "/portal/manufacturers/threads/{thread_id}/messages" in paths


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


def _confirm_manufacturer(db: object, company_id: int) -> None:  # noqa: ANN001
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        BusinessRoleStatus,
    )
    from app.models.enums import (
        CompanyBusinessRole as Role,
    )

    db.add(  # type: ignore[attr-defined]
        CompanyBusinessRole(
            company_id=company_id,
            role=Role.manufacturer,
            status=BusinessRoleStatus.confirmed,
        )
    )


@requires_real_db
def test_list_only_confirmed_manufacturers(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        m_owner = make_account(db, "+998900005001")
        manufacturer = make_company(
            db,
            m_owner,
            tax_id="315000001",
            legal_name="UzChem Plant",
            short_name="UzChem",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
            manufacturer_profile={
                "employees": 500,
                "founded_year": 2005,
                "iso_certification": "ISO 9001",
                "export_countries": ["GE", "TR"],
            },
        )
        _confirm_manufacturer(db, manufacturer.id)
        make_seller_offer(db, company=manufacturer, grade_text="PP-H250")

        trader_owner = make_account(db, "+998900005002")
        trader = make_company(
            db,
            trader_owner,
            tax_id="315000002",
            legal_name="Trader Co",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        make_seller_offer(db, company=trader, grade_text="TRADER-ONLY")

        viewer = make_account(db, "+998900005003")
        db.commit()
        viewer_id, manufacturer_id = viewer.id, manufacturer.id

    resp = client.get(_BASE, headers=_auth(viewer_id))
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert manufacturer_id in ids
    assert body["total"] >= 1
    card = next(i for i in body["items"] if i["id"] == manufacturer_id)
    assert card["short_name"] == "UzChem"
    assert card["employees"] == 500
    assert card["founded_year"] == 2005
    assert card["offer_count"] == 1
    assert "GE" in card["export_countries"]


@requires_real_db
def test_factory_rfq_and_chat_happy_path(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        m_owner = make_account(db, "+998900005101")
        manufacturer = make_company(
            db,
            m_owner,
            tax_id="315000101",
            legal_name="Factory One",
            short_name="Factory1",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _confirm_manufacturer(db, manufacturer.id)
        offer = make_seller_offer(db, company=manufacturer, grade_text="LDPE-FACTORY")

        buyer_owner = make_account(db, "+998900005102")
        buyer = make_company(
            db,
            buyer_owner,
            tax_id="315000102",
            legal_name="Buyer One",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        db.commit()
        ids = {
            "buyer_account": buyer_owner.id,
            "buyer_company": buyer.id,
            "manufacturer": manufacturer.id,
            "offer": offer.id,
        }

    # Open chat
    thread_resp = client.post(
        f"{_BASE}/{ids['manufacturer']}/threads",
        json={"company_id": ids["buyer_company"]},
        headers=_auth(ids["buyer_account"]),
    )
    assert thread_resp.status_code == 201
    thread = thread_resp.json()
    assert thread["manufacturer_company_id"] == ids["manufacturer"]
    assert thread["my_role"] == "buyer"

    # Idempotent open
    again = client.post(
        f"{_BASE}/{ids['manufacturer']}/threads",
        json={"company_id": ids["buyer_company"]},
        headers=_auth(ids["buyer_account"]),
    )
    assert again.status_code == 201
    assert again.json()["id"] == thread["id"]

    # Post message
    msg = client.post(
        f"{_BASE}/threads/{thread['id']}/messages",
        data={"company_id": str(ids["buyer_company"]), "body": "Hello factory"},
        headers=_auth(ids["buyer_account"]),
    )
    assert msg.status_code == 201
    assert msg.json()["body"] == "Hello factory"

    page = client.get(
        f"{_BASE}/threads/{thread['id']}/messages",
        params={"company_id": ids["buyer_company"]},
        headers=_auth(ids["buyer_account"]),
    )
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1

    # Create factory RFQ
    rfq_resp = client.post(
        f"{_BASE}/{ids['manufacturer']}/rfqs",
        json={
            "company_id": ids["buyer_company"],
            "offer_id": ids["offer"],
            "quantity": "25",
            "qty_unit": "MT",
            "target_price": "1100",
            "currency": "USD",
            "incoterms": "CIF",
            "destination_port": "Poti, Georgia",
            "payment_method": "L/C",
            "contact_name": "Ivan Petrov",
            "contact_phone": "+998901112233",
            "contact_email": "ivan@example.com",
        },
        headers=_auth(ids["buyer_account"]),
    )
    assert rfq_resp.status_code == 201, rfq_resp.text
    rfq = rfq_resp.json()
    assert rfq["number"].startswith("FRQ-")
    assert rfq["status"] == "submitted"
    assert rfq["offer_id"] == ids["offer"]
    assert rfq["quantity"] == "25.000"

    listed = client.get(
        f"{_BASE}/rfqs",
        params={"company_id": ids["buyer_company"], "side": "sent"},
        headers=_auth(ids["buyer_account"]),
    )
    assert listed.status_code == 200
    assert any(item["id"] == rfq["id"] for item in listed.json())

    # Self-RFQ rejected
    self_rfq = client.post(
        f"{_BASE}/{ids['manufacturer']}/rfqs",
        json={
            "company_id": ids["manufacturer"],
            "offer_id": ids["offer"],
            "quantity": "10",
            "contact_name": "Self",
            "contact_phone": "+998900000000",
        },
        headers=_auth(ids["buyer_account"]),
    )
    # buyer_account is not a member of manufacturer → 404 from company guard
    assert self_rfq.status_code in (403, 404, 422)
