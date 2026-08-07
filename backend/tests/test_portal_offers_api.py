"""Portal company-offer API tests (R1 W5 — T5.2).

Route reg DB-free; publish/list/edit/archive + unverified-403 + isolation against
test_polymer (guarded). REQUEST_NOTIFY_CHAT_ID is unset in tests, so the
group-notify enqueue is a no-op (no broker).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/companies"


def test_offer_routes_registered() -> None:
    from app.api.portal.offers import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/offers" in paths
    assert "/portal/companies/{company_id}/offers/{offer_id}" in paths
    assert "/portal/companies/{company_id}/offers/{offer_id}/archive" in paths


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
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
    from unittest.mock import patch  # noqa: PLC0415

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _company(session, phone: str, tax: str, *, verified: bool):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyBusinessRole, CompanyStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        # distributor+trader: publishes offers — the role gates (T-B) require it
        company_service.set_business_roles(
            db, company, [CompanyBusinessRole.distributor, CompanyBusinessRole.trader]
        )
        if verified:
            company.status = CompanyStatus.verified
        db.commit()
        return account.id, company.id


_OFFER = {"product_text": "HDPE 5502", "grade_text": "film", "price": "1200", "currency": "USD"}


@requires_real_db
def test_verified_company_publishes_offer_into_moderation(api) -> None:  # noqa: ANN001
    client, session = api
    account_id, company_id = _company(session, "+998900000001", "123456789", verified=True)

    created = client.post(f"{_BASE}/{company_id}/offers", json=_OFFER, headers=_auth(account_id))
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending_moderation"
    assert body["product_text"] == "HDPE 5502"

    listed = client.get(f"{_BASE}/{company_id}/offers", headers=_auth(account_id))
    assert [o["id"] for o in listed.json()] == [body["id"]]


@requires_real_db
def test_unverified_company_offer_is_403_typed(api) -> None:  # noqa: ANN001
    client, session = api
    account_id, company_id = _company(session, "+998900000001", "123456789", verified=False)

    resp = client.post(f"{_BASE}/{company_id}/offers", json=_OFFER, headers=_auth(account_id))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "company_not_verified"


@requires_real_db
def test_edit_approved_offer_requeues_to_moderation(api) -> None:  # noqa: ANN001
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.models.marketplace import SellerOffer  # noqa: PLC0415

    client, session = api
    account_id, company_id = _company(session, "+998900000001", "123456789", verified=True)
    offer_id = client.post(
        f"{_BASE}/{company_id}/offers", json=_OFFER, headers=_auth(account_id)
    ).json()["id"]

    # simulate approval, then a buyer-facing edit must re-enter moderation
    with session() as db:
        db.get(SellerOffer, offer_id).status = SellerOfferStatus.approved
        db.commit()

    edited = client.patch(
        f"{_BASE}/{company_id}/offers/{offer_id}",
        json={**_OFFER, "price": "1300"},
        headers=_auth(account_id),
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "pending_moderation"


@requires_real_db
def test_archive_and_membership_isolation(api) -> None:  # noqa: ANN001
    client, session = api
    account_a, company_id = _company(session, "+998900000001", "123456789", verified=True)
    account_b, _company_b = _company(session, "+998900000002", "987654321", verified=True)

    offer_id = client.post(
        f"{_BASE}/{company_id}/offers", json=_OFFER, headers=_auth(account_a)
    ).json()["id"]

    # account B (member of a different company) cannot see A's offers → 404
    assert client.get(f"{_BASE}/{company_id}/offers", headers=_auth(account_b)).status_code == 404
    assert (
        client.get(f"{_BASE}/{company_id}/offers/{offer_id}", headers=_auth(account_b)).status_code
        == 404
    )

    archived = client.post(
        f"{_BASE}/{company_id}/offers/{offer_id}/archive", headers=_auth(account_a)
    )
    assert archived.json()["status"] == "archived"
