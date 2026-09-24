"""Technologist marketplace over HTTP: who may call what, and what crosses the wire.

The service rules are in `test_tech_requests_db` / `test_technologist_profiles_db`;
this suite holds the API's own promises — the route order, the anonymous
catalog carrying no contacts, the feed hiding the factory, the side-resolution
of a thread, and 403/404 on the wrong caller.
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


def test_literal_routes_precede_parameterised_ones() -> None:
    from app.domains.technologists.api_portal import router as portal  # noqa: PLC0415
    from app.domains.technologists.api_public import router as public  # noqa: PLC0415

    public_paths = [r.path for r in public.routes]  # type: ignore[attr-defined]
    assert public_paths.index("/public/technologists/facets") < public_paths.index(
        "/public/technologists/{profile_id}"
    )
    portal_paths = [r.path for r in portal.routes]  # type: ignore[attr-defined]
    assert portal_paths.index("/portal/me/technologist/threads") < portal_paths.index(
        "/portal/me/technologist/requests/{request_id}"
    )


def test_public_models_cannot_carry_contacts() -> None:
    from app.domains.technologists.schemas import (  # noqa: PLC0415
        TechFeedItemOut,
        TechnologistCardOut,
    )

    assert not {"contact_phone", "contact_email", "phone", "email"} & set(
        TechnologistCardOut.model_fields
    )
    # The feed's only contact block is the explicit, gated `contacts`.
    assert not {"contact_phone", "phone"} & set(TechFeedItemOut.model_fields)


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


_PROFILE = {
    "full_name": "Akmal Karimov",
    "title": "Extrusion technologist",
    "country": "UZ",
    "years_experience": 12,
    "processes": ["film"],
    "languages": ["ru"],
    "work_formats": ["on_site"],
    "contact_phone": "+998901112233",
}

_REQUEST = {
    "need_type": "troubleshooting",
    "process": "film",
    "equipment": "Extrusion line",
    "product": "PE film",
    "problem": "Unstable thickness",
    "country": "UZ",
    "city": "Tashkent",
    "urgency": "urgent",
    "work_format": "on_site",
}

_OFFER = {
    "scope": "Line audit",
    "price": "1500",
    "currency": "USD",
    "duration_days": 3,
    "work_format": "on_site",
}


def _world(session) -> dict[str, int]:  # noqa: ANN001
    """A verified factory, an outsider company, an approved expert, a staff member."""
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists.schemas import TechnologistProfileIn  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with session() as db:
        owner = make_account(db, "+998900020001")
        factory = make_company(
            db, owner, tax_id="500000001", legal_name="Plenka LLC", status=CompanyStatus.verified
        )
        outsider_acc = make_account(db, "+998900020002")
        outsider = make_company(
            db, outsider_acc, tax_id="500000002", status=CompanyStatus.verified
        )
        expert = make_account(db, "+998900020003")
        expert.applied_as = "technologist"
        staff = make_staff(db)
        db.flush()
        profile = profiles.update_own(db, expert, TechnologistProfileIn(**_PROFILE))
        profiles.submit_own(db, expert)
        profiles.approve(db, profile, staff.id)
        db.commit()
        return {
            "owner": owner.id,
            "factory": factory.id,
            "outsider": outsider_acc.id,
            "outsider_company": outsider.id,
            "expert": expert.id,
            "profile": profile.id,
        }


@requires_real_db
def test_the_catalog_is_public_and_has_no_contacts(api) -> None:  # noqa: ANN001
    client, session = api
    w = _world(session)
    listing = client.get("/api/v1/public/technologists")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    card = client.get(f"/api/v1/public/technologists/{w['profile']}").json()
    assert card["full_name"] == "Akmal Karimov"
    assert "+998901112233" not in listing.text + str(card)
    assert client.get("/api/v1/public/technologists/facets").json()["processes"]
    assert client.get("/api/v1/public/technologists/999999").status_code == 404


@requires_real_db
def test_a_company_account_is_not_an_expert(api) -> None:  # noqa: ANN001
    client, session = api
    w = _world(session)
    resp = client.get("/api/v1/portal/me/technologist", headers=_auth(w["owner"]))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_a_technologist"


@requires_real_db
def test_submit_reports_missing_fields(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        account = make_account(db, "+998900020009")
        account.applied_as = "technologist"
        db.commit()
        account_id = account.id
    headers = _auth(account_id)
    assert client.get("/api/v1/portal/me/technologist", headers=headers).status_code == 200
    resp = client.post("/api/v1/portal/me/technologist/submit", headers=headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "profile_incomplete"
    assert "title" in detail["missing"]


@requires_real_db
def test_the_full_loop(api) -> None:  # noqa: ANN001
    client, session = api
    w = _world(session)
    factory_headers = _auth(w["owner"])
    expert_headers = _auth(w["expert"])
    base = f"/api/v1/portal/companies/{w['factory']}/tech-requests"

    created = client.post(base, json=_REQUEST, headers=factory_headers)
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    assert created.json()["number"].startswith("IMX-TECH-")

    # An outsider company cannot read it; an expert reads it anonymised.
    assert (
        client.get(
            f"/api/v1/portal/companies/{w['outsider_company']}/tech-requests/{request_id}",
            headers=_auth(w["outsider"]),
        ).status_code
        == 404
    )
    feed = client.get("/api/v1/portal/me/technologist/requests", headers=expert_headers).json()
    assert [i["id"] for i in feed["items"]] == [request_id]
    assert feed["items"][0]["company"] is None
    assert "Plenka" not in str(feed)

    offered = client.post(
        f"/api/v1/portal/me/technologist/requests/{request_id}/offer",
        json=_OFFER,
        headers=expert_headers,
    )
    assert offered.status_code == 201, offered.text
    item = offered.json()
    assert item["company"]["name"] == "Plenka LLC", "an offer opens the thread → name crosses"
    thread_id = item["my_thread_id"]
    assert item["contacts"] is None

    # Both sides talk in the same thread; `mine` is per side.
    assert (
        client.post(
            f"/api/v1/portal/tech-threads/{thread_id}/messages",
            data={"body": "Могу приехать в четверг"},
            headers=expert_headers,
        ).status_code
        == 201
    )
    reply = client.post(
        f"/api/v1/portal/tech-threads/{thread_id}/messages",
        data={"body": "Подходит", "company_id": str(w["factory"])},
        headers=factory_headers,
    )
    assert reply.status_code == 201
    as_expert = client.get(
        f"/api/v1/portal/tech-threads/{thread_id}/messages", headers=expert_headers
    ).json()["items"]
    assert [m["mine"] for m in as_expert] == [True, False]
    as_factory = client.get(
        f"/api/v1/portal/tech-threads/{thread_id}/messages",
        params={"company_id": w["factory"]},
        headers=factory_headers,
    ).json()["items"]
    assert [m["mine"] for m in as_factory] == [False, True]
    assert (
        client.get(
            f"/api/v1/portal/tech-threads/{thread_id}/messages",
            params={"company_id": w["outsider_company"]},
            headers=_auth(w["outsider"]),
        ).status_code
        == 404
    )

    offers = client.get(f"{base}/{request_id}/offers", headers=factory_headers).json()["items"]
    assert len(offers) == 1
    assert offers[0]["contacts"] is None
    offer_id = offers[0]["id"]

    accepted = client.post(f"{base}/{request_id}/offers/{offer_id}/accept", headers=factory_headers)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "assigned"

    offers = client.get(f"{base}/{request_id}/offers", headers=factory_headers).json()["items"]
    assert offers[0]["contacts"]["phone"] == "+998901112233"
    mine = client.get(
        f"/api/v1/portal/me/technologist/requests/{request_id}", headers=expert_headers
    ).json()
    assert mine["contacts"]["phone"] == "+998900020001"

    done = client.post(
        f"{base}/{request_id}/complete", json={"rating": 5, "text": "Спасибо"}, headers=factory_headers
    )
    assert done.status_code == 200
    card = client.get(f"/api/v1/public/technologists/{w['profile']}").json()
    assert card["rating_count"] == 1
    assert card["rating_avg"] == "5.00"


@requires_real_db
def test_a_second_offer_is_409(api) -> None:  # noqa: ANN001
    client, session = api
    w = _world(session)
    base = f"/api/v1/portal/companies/{w['factory']}/tech-requests"
    request_id = client.post(base, json=_REQUEST, headers=_auth(w["owner"])).json()["id"]
    url = f"/api/v1/portal/me/technologist/requests/{request_id}/offer"
    assert client.post(url, json=_OFFER, headers=_auth(w["expert"])).status_code == 201
    second = client.post(url, json=_OFFER, headers=_auth(w["expert"]))
    assert second.status_code == 409
    assert second.json()["detail"] == "offer_exists"


@requires_real_db
def test_an_unverified_factory_is_refused(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        owner = make_account(db, "+998900020011")
        company = make_company(db, owner, tax_id="500000011")
        db.commit()
        owner_id, company_id = owner.id, company.id
    resp = client.post(
        f"/api/v1/portal/companies/{company_id}/tech-requests",
        json=_REQUEST,
        headers=_auth(owner_id),
    )
    # The one shape every portal route refuses an unverified company in (IMEX-7).
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "company_not_verified"
