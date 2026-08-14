"""
Business-role badges in the API payloads (P4 W2 — T2.1).

Guarded (localhost test_polymer).

The rule that matters: a badge means CONFIRMED. A company declares its roles when
it registers and staff confirm them during verification, so showing a declared
role as a badge would let anyone self-award "manufacturer" — exactly the claim a
buyer is using the badge to check.

The other thing asserted here is that resolving roles for a page of companies
does not fan out into a query per row.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_P = "/api/v1/portal"


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


def _account(session, phone):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    return account_id, {
        "Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"
    }


def _seller_with_roles(session, account_id, tax, roles):  # noqa: ANN001, ANN202
    """A verified company publishing one approved offer, with the given roles.

    `roles` is a list of (role, status) so a test can mix confirmed and declared.
    """
    from app.core.time import utcnow  # noqa: PLC0415
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.enums import CompanyStatus, SellerOfferStatus  # noqa: PLC0415

    with session() as db:
        account = db.get(UserAccount, account_id)
        company = make_company(db, account, tax_id=tax)
        company.status = CompanyStatus.verified
        company.legal_name = f"OOO {tax}"
        db.flush()
        for role, role_status in roles:
            db.add(
                CompanyBusinessRole(company_id=company.id, role=role, status=role_status)
            )
        offer = make_seller_offer(db, company=company, status=SellerOfferStatus.approved)
        offer.published_at = utcnow()
        db.commit()
        return company.id, offer.id


@requires_real_db
def test_the_market_card_carries_confirmed_roles_only(api) -> None:  # noqa: ANN001
    """A declared-but-unconfirmed role must NOT become a badge: the badge is
    exactly the claim a buyer is using it to verify."""
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    buyer_id, headers = _account(session, "+998900000001")
    _seller_id, _account_h = _account(session, "+998900000002")
    _seller_with_roles(
        session,
        _seller_id,
        "302222222",
        [
            (Role.manufacturer, BusinessRoleStatus.confirmed),
            (Role.trader, BusinessRoleStatus.declared),
            (Role.importer, BusinessRoleStatus.revoked),
        ],
    )
    assert buyer_id

    card = client.get(f"{_P}/market", headers=headers).json()[0]
    assert card["business_roles"] == ["manufacturer"], (
        "declared and revoked roles must not appear as badges"
    )


@requires_real_db
def test_the_offer_detail_carries_them_too(api) -> None:  # noqa: ANN001
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    _buyer_id, headers = _account(session, "+998900000001")
    _seller_id, _h = _account(session, "+998900000002")
    _company_id, offer_id = _seller_with_roles(
        session, _seller_id, "302222222", [(Role.distributor, BusinessRoleStatus.confirmed)]
    )

    detail = client.get(f"{_P}/market/{offer_id}", headers=headers).json()
    assert detail["business_roles"] == ["distributor"]


@requires_real_db
def test_a_seller_origin_offer_has_no_roles(api) -> None:  # noqa: ANN001
    """A Telegram seller is not a portal company, so there is nothing to confirm."""
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from tests._verification_db import make_seller  # noqa: PLC0415

    client, session = api
    _buyer_id, headers = _account(session, "+998900000001")
    with session() as db:
        seller = make_seller(db, telegram_user_id=777001)
        offer = make_seller_offer(db, seller=seller, status=SellerOfferStatus.approved)
        offer.published_at = utcnow()
        db.commit()

    card = client.get(f"{_P}/market", headers=headers).json()[0]
    assert card["business_roles"] == []


@requires_real_db
def test_the_directory_shows_confirmed_roles_only(api) -> None:  # noqa: ANN001
    """The counterparty directory had the same bug: it listed every declared
    role, so any company could self-award "manufacturer" in the picker used to
    choose a contract counterparty."""
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    _viewer_id, headers = _account(session, "+998900000001")
    _seller_id, _h = _account(session, "+998900000002")
    _seller_with_roles(
        session,
        _seller_id,
        "302222222",
        [
            (Role.laboratory, BusinessRoleStatus.confirmed),
            (Role.manufacturer, BusinessRoleStatus.declared),
        ],
    )

    listed = client.get(f"{_P}/companies/directory", headers=headers).json()
    target = next(c for c in listed if c["tax_id"] == "302222222")
    assert target["roles"] == ["laboratory"]


@requires_real_db
def test_a_page_of_cards_does_not_fan_out_into_a_query_per_row(api) -> None:  # noqa: ANN001
    """Roles must be eager-loaded. The market list is the busiest screen in the
    portal, and a lazy relationship there is one SELECT per card."""
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    _buyer_id, headers = _account(session, "+998900000001")
    for index in range(5):
        seller_id, _h = _account(session, f"+99890000101{index}")
        _seller_with_roles(
            session,
            seller_id,
            f"30333333{index}",
            [(Role.manufacturer, BusinessRoleStatus.confirmed)],
        )

    statements: list[str] = []

    def _record(conn, cursor, statement, *args):  # noqa: ANN001, ANN202
        statements.append(statement)

    from app.core.db import engine as app_engine  # noqa: PLC0415

    assert app_engine is not None
    sa.event.listen(session.kw["bind"], "before_cursor_execute", _record)
    try:
        cards = client.get(f"{_P}/market", headers=headers).json()
    finally:
        sa.event.remove(session.kw["bind"], "before_cursor_execute", _record)

    assert len(cards) == 5
    role_queries = [s for s in statements if "company_business_roles" in s]
    assert len(role_queries) <= 1, (
        f"roles were lazy-loaded: {len(role_queries)} queries for 5 cards"
    )
