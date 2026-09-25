"""Account self-deletion against real Postgres — what the privacy policy promises.

`POST /portal/me/delete` end to end (real DB, FakeRedis): the person can no longer
sign in, their personal fields are gone from the row, their memberships are gone —
and the company, which is a legal record, is still there. Only a database can
refute these: the `deleted` ENUM value (0056) that a mocked suite accepts the
moment the Python member exists, the tombstone surviving ~40 foreign keys, and the
technologist card leaving the public catalog.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \\
        uv run pytest tests/test_account_deletion_db.py -q
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_member,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)

_DELETE = "/api/v1/portal/me/delete"
_LOGIN = "/api/v1/portal/auth/login"
_PASS = "correct horse battery"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine) -> Iterator[tuple[TestClient, object]]:
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    app = create_app()
    fake = FakeRedis()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = lambda: fake
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _person(db, phone: str, login: str):  # noqa: ANN001, ANN202
    """An active account with a REAL password hash — this suite signs in with it."""
    from app.core.security import hash_password  # noqa: PLC0415

    account = make_account(db, phone)
    account.login = login
    account.password_hash = hash_password(_PASS)
    account.name = "Иван Петров"
    account.telegram_user_id = 123456789
    account.applied_company_name = "ООО Полимер"
    account.application_note = "Позвоните после обеда"
    db.flush()
    return account


def _sign_in(client: TestClient, login: str) -> dict[str, str]:
    resp = client.post(_LOGIN, json={"login": login, "password": _PASS})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@requires_real_db
def test_deletion_scrubs_the_person_and_keeps_the_company(api) -> None:  # noqa: ANN001
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.domains.companies.models import Company, CompanyMember  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415
    from app.models.staff import AuditLog  # noqa: PLC0415

    client, session = api
    with session() as db:
        person = _person(db, "+998900030001", "ivan-petrov")
        colleague = make_account(db, "+998900030002")
        own = make_company(db, person, tax_id="600000001", legal_name="Own LLC")
        shared = make_company(db, colleague, tax_id="600000002", legal_name="Shared LLC")
        make_member(db, shared, person)
        db.commit()
        person_id, own_id, shared_id = person.id, own.id, shared.id

    headers = _sign_in(client, "ivan-petrov")
    resp = client.post(_DELETE, json={"password": _PASS}, headers=headers)
    assert resp.status_code == 204
    assert "portal_session=" in resp.headers.get("set-cookie", "")

    # Cannot sign in again — not with the old login, not with the old token.
    assert (
        client.post(_LOGIN, json={"login": "ivan-petrov", "password": _PASS}).status_code == 401
    )
    assert client.get("/api/v1/portal/me", headers=headers).status_code == 403

    with session() as db:
        row = db.get(UserAccount, person_id)
        assert row is not None  # a tombstone, not a hole behind ~40 foreign keys
        assert row.status == AccountStatus.deleted
        assert row.login is None
        assert row.password_hash is None
        assert row.name is None
        assert row.telegram_user_id is None
        assert row.applied_company_name is None
        assert row.application_note is None
        assert "+998900030001" not in row.phone

        members = db.execute(
            sa.select(CompanyMember).where(CompanyMember.user_account_id == person_id)
        ).scalars().all()
        assert members == []
        # Both companies survive — they are the legal entity's records.
        assert db.get(Company, own_id) is not None
        assert db.get(Company, shared_id) is not None
        # The colleague's membership is untouched.
        assert db.execute(
            sa.select(sa.func.count())
            .select_from(CompanyMember)
            .where(CompanyMember.company_id == shared_id)
        ).scalar_one() == 1

        audit = db.execute(
            sa.select(AuditLog).where(AuditLog.action == "portal_account.self_deleted")
        ).scalar_one()
        assert audit.entity_id == str(person_id)
        assert sorted(audit.details["companies_left"]) == sorted([own_id, shared_id])
        assert "ivan-petrov" not in str(audit.details)


@requires_real_db
def test_a_wrong_password_changes_nothing(api) -> None:  # noqa: ANN001
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        person = _person(db, "+998900030011", "keep-me")
        db.commit()
        person_id = person.id

    headers = _sign_in(client, "keep-me")
    resp = client.post(_DELETE, json={"password": "wrong"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json() == {"detail": "invalid_password"}

    with session() as db:
        row = db.get(UserAccount, person_id)
        assert row is not None
        assert row.status == AccountStatus.active
        assert row.login == "keep-me"
    assert client.get("/api/v1/portal/me", headers=headers).status_code == 200


@requires_real_db
def test_unauthenticated_is_401(api) -> None:  # noqa: ANN001
    client, _session = api
    assert client.post(_DELETE, json={"password": _PASS}).status_code == 401


@requires_real_db
def test_a_technologist_leaves_the_catalog_and_loses_their_contacts(api) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists.models import TechnologistProfile  # noqa: PLC0415
    from app.domains.technologists.schemas import TechnologistProfileIn  # noqa: PLC0415

    client, session = api
    with session() as db:
        expert = _person(db, "+998900030021", "akmal-tech")
        expert.applied_as = "technologist"
        staff = make_staff(db)
        db.flush()
        profile = profiles.update_own(
            db,
            expert,
            TechnologistProfileIn(
                full_name="Akmal Karimov",
                title="Extrusion technologist",
                country="UZ",
                years_experience=12,
                processes=["film"],
                languages=["ru"],
                work_formats=["on_site"],
                contact_phone="+998901112233",
                contact_email="akmal@example.com",
            ),
        )
        profiles.submit_own(db, expert)
        profiles.approve(db, profile, staff.id)
        db.commit()
        profile_id = profile.id

    assert client.get("/api/v1/public/technologists").json()["total"] == 1

    headers = _sign_in(client, "akmal-tech")
    assert client.post(_DELETE, json={"password": _PASS}, headers=headers).status_code == 204

    assert client.get("/api/v1/public/technologists").json()["total"] == 0
    assert client.get(f"/api/v1/public/technologists/{profile_id}").status_code == 404
    with session() as db:
        row = db.get(TechnologistProfile, profile_id)
        assert row is not None
        assert row.status == "suspended"
        assert row.published_snapshot is None
        assert row.full_name is None
        assert row.contact_phone is None
        assert row.contact_email is None
        assert row.photo_key is None
