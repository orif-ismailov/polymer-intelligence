"""Offer product facts — manufacturer / key_properties / applications (0030).

The three fields the redesigned add-product flow collects that the offer row had
nowhere to put. Schema behaviour is DB-free; the round trip is guarded.
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


# ── Schema (DB-free) ──────────────────────────────────────────────────────────


def test_chips_default_to_empty_lists() -> None:
    from app.domains.companies.schemas import CompanyOfferIn

    payload = CompanyOfferIn(product_text="PP H030 GP")
    assert payload.key_properties == []
    assert payload.applications == []
    assert payload.manufacturer is None


def test_chips_are_trimmed_and_blanks_dropped() -> None:
    from app.domains.companies.schemas import CompanyOfferIn

    payload = CompanyOfferIn(
        product_text="PP H030 GP",
        key_properties=["  MFI: 3.0 г/10мин ", "", "   ", "Плотность: 0.90 г/см³"],
        applications=["Упаковка "],
    )
    assert payload.key_properties == ["MFI: 3.0 г/10мин", "Плотность: 0.90 г/см³"]
    assert payload.applications == ["Упаковка"]


def test_a_chip_is_capped_at_eighty_characters() -> None:
    """A pill is a phrase. Truncating beats rejecting: the seller keeps the save."""
    from app.domains.companies.schemas import CompanyOfferIn

    payload = CompanyOfferIn(product_text="PP", key_properties=["x" * 200])
    assert payload.key_properties == ["x" * 80]


def test_too_many_chips_is_rejected() -> None:
    from pydantic import ValidationError

    from app.domains.companies.schemas import CompanyOfferIn

    with pytest.raises(ValidationError):
        CompanyOfferIn(product_text="PP", applications=[f"use {i}" for i in range(13)])


def test_out_schema_reads_null_columns_as_empty_lists() -> None:
    """The columns are nullable and 0030 backfilled nothing, so every row that
    predates the flow arrives with NULL — the client must not have to tell that
    apart from "the seller cleared the chips"."""
    import datetime

    from app.domains.companies.schemas import CompanyOfferOut
    from app.models.enums import OfferAvailability, PriceBasis, SellerOfferStatus

    class _Row:
        id = 1
        status = SellerOfferStatus.draft
        availability = OfferAvailability.in_stock
        qty_unit = "MT"
        currency = "USD"
        incoterms = PriceBasis.unknown
        created_at = datetime.datetime(2026, 7, 30, tzinfo=datetime.UTC)
        manufacturer = None
        key_properties = None
        applications = None

    out = CompanyOfferOut.model_validate(_Row(), from_attributes=True)
    assert out.key_properties == []
    assert out.applications == []


# ── Round trip (guarded) ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from app.core.db import get_db
    from app.core.redis import get_redis
    from app.main import create_app
    from tests._fake_redis import FakeRedis

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
    from unittest.mock import patch

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _verified_company(session, phone: str, tax: str):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service
    from app.models.enums import CompanyBusinessRole, CompanyStatus

    with session() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        # distributor+trader: publishes offers — the role gates (T-B) require it
        company_service.set_business_roles(
            db, company, [CompanyBusinessRole.distributor, CompanyBusinessRole.trader]
        )
        company.status = CompanyStatus.verified
        db.commit()
        return account.id, company.id


@requires_real_db
def test_product_facts_survive_create_and_edit(api) -> None:  # noqa: ANN001
    client, session = api
    account_id, company_id = _verified_company(session, "+998900000001", "123456789")

    created = client.post(
        f"{_BASE}/{company_id}/offers",
        json={
            "product_text": "PP H030 GP",
            "manufacturer": "Sibur",
            "key_properties": ["MFI: 3.0 г/10мин", "Плотность: 0.90 г/см³"],
            "applications": ["Литьё под давлением", "Упаковка"],
        },
        headers=_auth(account_id),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["manufacturer"] == "Sibur"
    assert body["key_properties"] == ["MFI: 3.0 г/10мин", "Плотность: 0.90 г/см³"]
    assert body["applications"] == ["Литьё под давлением", "Упаковка"]

    # A full-replacement edit clears what it omits — the chips are no exception.
    edited = client.patch(
        f"{_BASE}/{company_id}/offers/{body['id']}",
        json={"product_text": "PP H030 GP", "manufacturer": "Shurtan GCC"},
        headers=_auth(account_id),
    )
    assert edited.status_code == 200
    assert edited.json()["manufacturer"] == "Shurtan GCC"
    assert edited.json()["key_properties"] == []
