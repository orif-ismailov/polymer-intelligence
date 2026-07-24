"""Real-Postgres tests for company_service (R1 W4 — T4.1 acceptance).

Guarded (localhost test_polymer only). Covers the stateful behaviours the pure
unit tests can't reach: persistence + owner membership + outbox event, the
(jurisdiction, tax_id) uniqueness → CompanyAlreadyRegistered (savepoint keeps the
session usable), membership isolation (non-member → 404 semantics), profile-edit
gating, business-role replacement, encrypted bank accounts, and the last-owner guard.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


@requires_real_db
def test_create_company_persists_owner_member_and_event(sf) -> None:  # noqa: ANN001
    from app.models.companies import Company, CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.models.staff import AuditLog  # noqa: PLC0415
    from app.services import company_service, event_types  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        db.commit()
        cid = company.id

    with sf() as db:
        company = db.get(Company, cid)
        assert company is not None
        assert company.status == CompanyStatus.draft
        members = db.query(CompanyMember).filter(CompanyMember.company_id == cid).all()
        assert len(members) == 1
        assert members[0].member_role == CompanyMemberRole.owner
        events = (
            db.query(DomainEvent)
            .filter(
                DomainEvent.event_type == event_types.COMPANY_REGISTERED,
                DomainEvent.aggregate_id == str(cid),
            )
            .all()
        )
        assert len(events) == 1
        audits = db.query(AuditLog).filter(AuditLog.action == "company.create").all()
        assert len(audits) == 1


@requires_real_db
def test_duplicate_tax_id_raises_and_session_stays_usable(sf) -> None:  # noqa: ANN001
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company_service.create_company(db, account, "UZ", "123456789")
        db.commit()

        with pytest.raises(company_service.CompanyAlreadyRegistered):
            company_service.create_company(db, account, "UZ", "123456789")

        # The savepoint rolled back only the failed insert — the session is still usable.
        second = company_service.create_company(db, account, "UZ", "987654321")
        db.commit()
        assert second.id is not None


@requires_real_db
def test_membership_isolation_returns_not_found_for_non_member(sf) -> None:  # noqa: ANN001
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account_a = make_account(db, "+998900000001")
        account_b = make_account(db, "+998900000002")
        company = company_service.create_company(db, account_a, "UZ", "123456789")
        db.commit()

        assert company_service.get_company_for(db, account_a, company.id).id == company.id
        with pytest.raises(company_service.CompanyNotFound):
            company_service.get_company_for(db, account_b, company.id)
        assert company_service.list_my_companies(db, account_b) == []
        assert [c.id for c in company_service.list_my_companies(db, account_a)] == [company.id]


@requires_real_db
def test_update_profile_gating(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415
    from app.models.verification import VerificationCase  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        db.commit()

        # draft → editable
        company_service.update_profile(db, company, account, legal_name="OOO Test", director_name="Ivanov")
        db.commit()
        assert company.legal_name == "OOO Test"

        # pending_verification without a needs_info case → NOT editable
        company.status = CompanyStatus.pending_verification
        db.commit()
        with pytest.raises(company_service.ProfileNotEditable):
            company_service.update_profile(db, company, account, legal_name="X")

        # a needs_info case re-opens editing
        db.add(VerificationCase(company_id=company.id, status=VerificationCaseStatus.needs_info))
        db.commit()
        company_service.update_profile(db, company, account, legal_name="OOO Fixed")
        db.commit()
        assert company.legal_name == "OOO Fixed"


@requires_real_db
def test_set_business_roles_replaces(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        db.commit()

        company_service.set_business_roles(
            db, company, [CompanyBusinessRole.manufacturer, CompanyBusinessRole.trader]
        )
        db.commit()
        db.refresh(company)
        assert {r.role for r in company.business_roles} == {
            CompanyBusinessRole.manufacturer,
            CompanyBusinessRole.trader,
        }

        # replace (not append)
        company_service.set_business_roles(db, company, [CompanyBusinessRole.importer])
        db.commit()
        db.refresh(company)
        assert {r.role for r in company.business_roles} == {CompanyBusinessRole.importer}


@requires_real_db
def test_add_bank_account_persists_encrypted(sf) -> None:  # noqa: ANN001
    from app.core.crypto import decrypt_pii  # noqa: PLC0415
    from app.models.companies import CompanyBankAccount  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        db.commit()

        company_service.add_bank_account(db, company, "00014", "20208000900040041234")
        db.commit()

        row = db.query(CompanyBankAccount).filter(CompanyBankAccount.company_id == company.id).one()
        assert row.account_last4 == "1234"
        assert decrypt_pii(row.account_number_enc) == "20208000900040041234"


@requires_real_db
def test_last_owner_guard(sf) -> None:  # noqa: ANN001
    from app.models.companies import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account_a = make_account(db, "+998900000001")
        company = company_service.create_company(db, account_a, "UZ", "123456789")
        db.commit()

        # sole owner: cannot be removed or demoted
        with pytest.raises(company_service.LastOwnerRemoval):
            company_service.remove_member(db, company, account_a.id)
        with pytest.raises(company_service.LastOwnerRemoval):
            company_service.set_member_role(db, company, account_a.id, CompanyMemberRole.manager)

        # add a second owner → the first may now be removed
        account_b = make_account(db, "+998900000002")
        db.add(
            CompanyMember(
                company_id=company.id,
                user_account_id=account_b.id,
                member_role=CompanyMemberRole.owner,
                status=CompanyMemberStatus.active,
            )
        )
        db.commit()
        company_service.remove_member(db, company, account_a.id)
        db.commit()
        assert company_service._active_owner_count(db, company.id) == 1
