"""Admin verification API tests (R1 W5 — T5.4).

Route + settings registration DB-free. Authz matrix, case decisions, waive, and
suspend→archive-offers against test_polymer (guarded, real staff JWTs).
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
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)


def test_routes_and_settings_registered() -> None:
    from app.domains.verification.api_admin import router  # noqa: PLC0415
    from app.services.settings_service import _SPECS  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/verification/cases" in paths
    assert "/admin/verification/cases/{case_id}/approve" in paths
    assert "/admin/verification/checks/{check_id}/waive" in paths
    assert "/admin/companies/{company_id}/suspend" in paths
    assert "bank_verification_required" in _SPECS
    assert "verification_required_for_publish" in _SPECS


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    monkeypatch.setattr("app.domains.verification.service._dispatch_checks", lambda case_id: None)
    monkeypatch.setattr("app.core.db.SessionLocal", session)  # for the archive task
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    from unittest.mock import patch  # noqa: PLC0415

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _staff_auth(session, role: str, email: str) -> dict[str, str]:  # noqa: ANN001
    from app.core.security import create_access_token  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        from app.models.enums import StaffRole  # noqa: PLC0415

        staff.role = StaffRole(role)
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"}


def _pending_review_case(session, phone: str, tax: str) -> tuple[int, int]:  # noqa: ANN001
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckStatus, VerificationCheckType  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        verification_service.open_case(db, company)
        case = verification_service.submit_case(db, company, account)
        for check in db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id):
            if check.check_type != VerificationCheckType.manual_kyb:
                check.status = VerificationCheckStatus.passed
        db.flush()
        verification_service.on_check_completed(db, case.id)
        db.commit()
        return company.id, case.id


# ── authz ─────────────────────────────────────────────────────────────────────


@requires_real_db
def test_cases_authz(api) -> None:  # noqa: ANN001
    client, session = api
    assert client.get("/api/v1/admin/verification/cases").status_code == 401
    viewer = _staff_auth(session, "viewer", "v@x.com")
    assert client.get("/api/v1/admin/verification/cases", headers=viewer).status_code == 403
    analyst = _staff_auth(session, "analyst", "a@x.com")
    assert client.get("/api/v1/admin/verification/cases", headers=analyst).status_code == 200


@requires_real_db
def test_approve_case_verifies_company(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    company_id, case_id = _pending_review_case(session, "+998900000001", "123456789")
    analyst = _staff_auth(session, "analyst", "a@x.com")

    resp = client.post(
        f"/api/v1/admin/verification/cases/{case_id}/approve", json={"note": "ok"}, headers=analyst
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    with session() as db:
        assert db.get(Company, company_id).status == CompanyStatus.verified

    # a second approve is idempotent → 409
    assert (
        client.post(
            f"/api/v1/admin/verification/cases/{case_id}/approve", json={}, headers=analyst
        ).status_code
        == 409
    )


@requires_real_db
def test_waive_requires_admin(api) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckType  # noqa: PLC0415

    client, session = api
    _company_id, case_id = _pending_review_case(session, "+998900000002", "222222222")
    with session() as db:
        check_id = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case_id,
                VerificationCheck.check_type == VerificationCheckType.manual_kyb,
            )
            .one()
            .id
        )

    analyst = _staff_auth(session, "analyst", "a@x.com")
    admin = _staff_auth(session, "admin", "adm@x.com")
    assert client.post(
        f"/api/v1/admin/verification/checks/{check_id}/waive", json={"reason": "ok"}, headers=analyst
    ).status_code == 403
    assert client.post(
        f"/api/v1/admin/verification/checks/{check_id}/waive", json={"reason": "ok"}, headers=admin
    ).status_code == 200


@requires_real_db
def test_suspend_archives_approved_offers(api) -> None:  # noqa: ANN001
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.models.enums import CompanyStatus, SellerOfferStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.verification import archive_company_offers  # noqa: PLC0415

    client, session = api
    with session() as db:
        account = make_account(db, "+998900000003")
        company = company_service.create_company(db, account, "UZ", "333333333")
        company.status = CompanyStatus.verified
        db.add(SellerOffer(company_id=company.id, created_by_user_account_id=account.id,
                           status=SellerOfferStatus.approved, availability="in_stock",
                           qty_unit="MT", currency="USD", incoterms="unknown"))
        db.commit()
        company_id = company.id

    admin = _staff_auth(session, "admin", "adm@x.com")
    resp = client.post(f"/api/v1/admin/companies/{company_id}/suspend", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"

    with session() as db:
        assert (
            db.query(DomainEvent)
            .filter(DomainEvent.event_type == event_types.COMPANY_SUSPENDED)
            .count()
            == 1
        )

    # the COMPANY_SUSPENDED consumer archives approved offers
    archive_company_offers(payload={"company_id": company_id})
    with session() as db:
        offer = db.query(SellerOffer).filter(SellerOffer.company_id == company_id).one()
        assert offer.status == SellerOfferStatus.archived

    # reinstate → verified again
    assert client.post(f"/api/v1/admin/companies/{company_id}/reinstate", headers=admin).json()["status"] == "verified"


# ── declared/confirmed roles + account-type profiles ───────────────────────────


@requires_real_db
def test_company_detail_splits_declared_and_confirmed_roles(api) -> None:  # noqa: ANN001
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as RoleEnum  # noqa: PLC0415

    client, session = api
    with session() as db:
        account = make_account(db, "+998900000010")
        company = make_company(
            db,
            account,
            "410000001",
            roles=["logistics_provider"],
            logistics_profile={"city": "Tashkent", "services": ["fcl"]},
        )
        db.query(CompanyBusinessRole).filter(
            CompanyBusinessRole.company_id == company.id,
            CompanyBusinessRole.role == RoleEnum.logistics_provider,
        ).update({"status": BusinessRoleStatus.confirmed})
        db.commit()
        company_id = company.id

    analyst = _staff_auth(session, "analyst", "roles-a@x.com")
    resp = client.get(f"/api/v1/admin/companies/{company_id}", headers=analyst)
    assert resp.status_code == 200
    body = resp.json()
    assert body["confirmed_roles"] == ["logistics_provider"]
    assert body["declared_roles"] == ["logistics_provider"]
    assert body["logistics_profile"] == {"city": "Tashkent", "services": ["fcl"]}
    assert body["manufacturer_profile"] is None
    assert body["laboratory_profile"] is None


@requires_real_db
def test_company_detail_declared_only_role_excluded_from_confirmed(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        account = make_account(db, "+998900000011")
        company = make_company(db, account, "410000002", roles=["laboratory"])
        db.commit()
        company_id = company.id

    analyst = _staff_auth(session, "analyst", "roles-b@x.com")
    resp = client.get(f"/api/v1/admin/companies/{company_id}", headers=analyst)
    assert resp.status_code == 200
    body = resp.json()
    assert body["declared_roles"] == ["laboratory"]
    assert body["confirmed_roles"] == []


@requires_real_db
def test_verification_case_company_includes_roles_and_profile(api) -> None:  # noqa: ANN001
    client, session = api
    _company_id, case_id = _pending_review_case(session, "+998900000012", "410000003")

    analyst = _staff_auth(session, "analyst", "roles-c@x.com")
    resp = client.get(f"/api/v1/admin/verification/cases/{case_id}", headers=analyst)
    assert resp.status_code == 200
    company = resp.json()["company"]
    assert "declared_roles" in company
    assert "confirmed_roles" in company
    assert "manufacturer_profile" in company
    assert "logistics_profile" in company
    assert "laboratory_profile" in company
