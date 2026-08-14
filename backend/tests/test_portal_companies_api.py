"""Portal companies API tests (R1 W5 — T5.1).

Route registration is DB-free. The CRUD / membership-isolation / verification /
document behaviour runs against test_polymer (guarded), driving real portal
tokens through get_current_account so auth + membership scoping are exercised
end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

_BASE = "/api/v1/portal/companies"


def test_routes_registered() -> None:
    """Both routers that serve `/portal/companies`, asserted together.

    P2 carved the documents + verification routes out of the companies router into
    the verification domain. The URL contract is unchanged — both routers share the
    `/portal/companies` prefix — so this test now names which router owns what,
    rather than assuming one owns everything.
    """
    from app.domains.companies.api_portal import router  # noqa: PLC0415
    from app.domains.verification.api_portal import router as verification_router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies" in paths
    assert "/portal/companies/{company_id}" in paths
    assert "/portal/companies/{company_id}/bank-accounts" in paths

    verification_paths = {r.path for r in verification_router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/verification/submit" in verification_paths
    assert "/portal/companies/{company_id}/verification" in verification_paths
    assert "/portal/companies/{company_id}/documents" in verification_paths
    assert "/portal/companies/{company_id}/documents/{document_id}/download" in verification_paths


# ── real-DB API fixture ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    # the verify-task dispatch on submit must not hit a broker
    monkeypatch.setattr("app.domains.verification.service._dispatch_checks", lambda case_id: None)

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


def _seed_account(session, phone: str) -> tuple[int, dict[str, str]]:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    token = create_portal_access_token(subject=str(account_id))
    return account_id, {"Authorization": f"Bearer {token}"}


# ── CRUD + verification ───────────────────────────────────────────────────────


@requires_real_db
def test_create_lists_and_details_company(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")

    created = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "draft"
    assert body["active_case"]["status"] == "draft"
    company_id = body["id"]

    listed = client.get(_BASE, headers=auth)
    assert [c["id"] for c in listed.json()] == [company_id]

    detail = client.get(f"{_BASE}/{company_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["tax_id"] == "123456789"


@requires_real_db
def test_bad_tax_id_and_duplicate(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")

    assert client.post(_BASE, json={"tax_id": "123"}, headers=auth).status_code == 422
    assert client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).status_code == 201
    assert client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).status_code == 409


@requires_real_db
def test_membership_isolation_404(api) -> None:  # noqa: ANN001
    client, session = api
    _a, auth_a = _seed_account(session, "+998900000001")
    _b, auth_b = _seed_account(session, "+998900000002")

    company_id = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth_a).json()["id"]

    assert client.get(f"{_BASE}/{company_id}", headers=auth_b).status_code == 404
    assert client.get(_BASE, headers=auth_b).json() == []
    # a non-member's PATCH is also a 404 (never reveals existence)
    assert client.patch(f"{_BASE}/{company_id}", json={"legal_name": "x"}, headers=auth_b).status_code == 404


@requires_real_db
def test_profile_roles_and_bank_masking(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")
    company_id = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).json()["id"]

    client.patch(f"{_BASE}/{company_id}", json={"legal_name": "OOO Test"}, headers=auth)
    client.put(
        f"{_BASE}/{company_id}/roles",
        json={"roles": ["distributor", "trader"]},
        headers=auth,
    )
    bank = client.post(
        f"{_BASE}/{company_id}/bank-accounts",
        json={"bank_mfo": "00014", "account_number": "20208000900040041234"},
        headers=auth,
    )
    assert bank.status_code == 201
    detail = bank.json()
    assert detail["legal_name"] == "OOO Test"
    assert {r["role"] for r in detail["roles"]} == {"distributor", "trader"}
    assert detail["bank_accounts"][0]["account_masked"] == "****1234"
    assert "20208000900040041234" not in str(detail)  # full number never serialized


@requires_real_db
def test_summary_carries_declared_roles(api) -> None:  # noqa: ANN001
    """The cabinet shapes itself on `declared_roles` (non-revoked declared+confirmed)."""
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415

    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")
    company_id = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).json()["id"]
    client.put(f"{_BASE}/{company_id}/roles", json={"roles": ["laboratory"]}, headers=auth)

    summary = client.get(_BASE, headers=auth).json()[0]
    assert summary["declared_roles"] == ["laboratory"]
    assert summary["confirmed_roles"] == []  # not staff-vouched yet

    # confirmed roles stay in declared_roles (it is the non-revoked set)
    with session() as db:
        row = db.query(CompanyBusinessRole).filter_by(company_id=company_id).one()
        row.status = BusinessRoleStatus.confirmed
        db.commit()
    summary = client.get(_BASE, headers=auth).json()[0]
    assert summary["declared_roles"] == ["laboratory"]
    assert summary["confirmed_roles"] == ["laboratory"]

    # revoked roles drop out of both
    with session() as db:
        row = db.query(CompanyBusinessRole).filter_by(company_id=company_id).one()
        row.status = BusinessRoleStatus.revoked
        db.commit()
    summary = client.get(_BASE, headers=auth).json()[0]
    assert summary["declared_roles"] == []
    assert summary["confirmed_roles"] == []


@requires_real_db
def test_roles_reject_cross_account_type_mix(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000011")
    company_id = client.post(_BASE, json={"tax_id": "123456790"}, headers=auth).json()["id"]

    resp = client.put(
        f"{_BASE}/{company_id}/roles",
        json={"roles": ["manufacturer", "trader"]},
        headers=auth,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "roles_span_multiple_account_types"


@requires_real_db
def test_submit_verification_runs_checks(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")
    company_id = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).json()["id"]

    submitted = client.post(f"{_BASE}/{company_id}/verification/submit", headers=auth)
    assert submitted.status_code == 200
    case = submitted.json()
    assert case["status"] == "checks_running"
    assert {c["check_type"] for c in case["checks"]} == {
        "tax_id_format",
        "bank_requisites",
        "documents_complete",
        "manual_kyb",
    }
    # user-safe checks: no reviewer identity / internals leaked
    assert "waived_by" not in str(case)
    assert "last_error" not in str(case)


@requires_real_db
def test_company_create_is_rate_limited(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")
    # 5/day/account: five succeed, the sixth is 429 with Retry-After
    for i in range(5):
        assert client.post(_BASE, json={"tax_id": f"12345678{i}"}, headers=auth).status_code == 201
    limited = client.post(_BASE, json={"tax_id": "999999999"}, headers=auth)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


@requires_real_db
def test_document_upload_download_delete(api) -> None:  # noqa: ANN001
    client, session = api
    _aid, auth = _seed_account(session, "+998900000001")
    company_id = client.post(_BASE, json={"tax_id": "123456789"}, headers=auth).json()["id"]

    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = "https://minio/presigned"
    with patch("app.core.storage.s3_client", fake_s3):
        up = client.post(
            f"{_BASE}/{company_id}/documents",
            data={"kind": "registration_certificate"},
            files={"file": ("cert.pdf", b"%PDF-1.4 hello", "application/pdf")},
            headers=auth,
        )
        assert up.status_code == 201
        document_id = up.json()["id"]

        dl = client.get(
            f"{_BASE}/{company_id}/documents/{document_id}/download",
            headers=auth,
            follow_redirects=False,
        )
        assert dl.status_code == 307
        assert dl.headers["location"] == "https://minio/presigned"

    # a pending_review document may be deleted
    assert client.delete(f"{_BASE}/{company_id}/documents/{document_id}", headers=auth).status_code == 204


def _account(db, account_id: int):  # noqa: ANN001, ANN202
    """Re-attach a seeded account to the session `make_company` will write in."""
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415

    return db.get(UserAccount, account_id)


# ── Storefront copy on a verified company ─────────────────────────────────────


def test_public_profile_route_registered() -> None:
    from app.domains.companies.api_portal import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/public-profile" in paths


@requires_real_db
def test_verified_company_can_edit_its_storefront_copy(api) -> None:  # noqa: ANN001
    """The blocker this endpoint exists for.

    `_assert_profile_editable` refuses anything past `draft`/undecided-case, and
    `directory_service` only lists `verified` companies — so a carrier's public
    page renders copy that `PATCH /{company_id}` can never again change. Both
    halves are asserted: the ordinary route still 409s, and the narrow one works.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    account_id, auth = _seed_account(session, "+998900000401")

    with session() as db:
        account = _account(db, account_id)
        company = make_company(
            db,
            account,
            tax_id="401000401",
            legal_name="Trans Asia Logistics",
            status=CompanyStatus.verified,
            logistics_profile={"services": ["rail"], "cargo_types": ["big_bags"]},
        )
        db.commit()
        company_id = company.id

    # The ordinary profile PATCH is closed on a verified company...
    frozen = client.patch(
        f"{_BASE}/{company_id}", json={"legal_address": "somewhere else"}, headers=auth
    )
    assert frozen.status_code == 409

    # ...but the storefront copy is not.
    res = client.patch(
        f"{_BASE}/{company_id}/public-profile",
        json={
            "logistics": {
                "description": "Международные перевозки нефтехимической продукции.",
                "years_experience": 12,
                "projects_completed": 1200,
            }
        },
        headers=auth,
    )
    assert res.status_code == 200

    profile = res.json()["logistics_profile"]
    assert profile["years_experience"] == 12
    assert profile["projects_completed"] == 1200
    # The merge is the other half: an unsent key keeps what registration collected.
    assert profile["services"] == ["rail"]
    assert profile["cargo_types"] == ["big_bags"]


@requires_real_db
def test_public_profile_cannot_reach_a_requisite(api) -> None:  # noqa: ANN001
    """Unknown keys are dropped, not merged.

    The whole justification for skipping the editability gate is that this door
    is narrow. A body naming `legal_name` must leave the verified column alone —
    otherwise this endpoint is just `update_profile` with the check removed.
    """
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    account_id, auth = _seed_account(session, "+998900000402")

    with session() as db:
        account = _account(db, account_id)
        company = make_company(
            db,
            account,
            tax_id="401000402",
            legal_name="Verified Name",
            status=CompanyStatus.verified,
            logistics_profile={"services": ["sea"]},
        )
        db.commit()
        company_id = company.id

    res = client.patch(
        f"{_BASE}/{company_id}/public-profile",
        json={"logistics": {"description": "ok", "legal_name": "Renamed By Client"}},
        headers=auth,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["legal_name"] == "Verified Name"
    assert "legal_name" not in body["logistics_profile"]


@requires_real_db
def test_public_profile_is_owner_only(api) -> None:  # noqa: ANN001
    """A non-member gets 404 (existence-hiding), never 403."""
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    owner_id, _owner_auth = _seed_account(session, "+998900000403")
    _outsider_id, outsider_auth = _seed_account(session, "+998900000404")

    with session() as db:
        owner = _account(db, owner_id)
        company = make_company(
            db, owner, tax_id="401000403", status=CompanyStatus.verified
        )
        db.commit()
        company_id = company.id

    res = client.patch(
        f"{_BASE}/{company_id}/public-profile",
        json={"logistics": {"description": "not mine"}},
        headers=outsider_auth,
    )
    assert res.status_code == 404
