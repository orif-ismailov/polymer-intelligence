"""Real-Postgres tests for verification_service (R1 W4 — T4.2 acceptance).

Guarded (localhost test_polymer). Covers case open/submit, the evaluator's
branches (needs_info / pending_review / auto-approve), the human decisions
(approve/reject/request_info) with the optimistic double-decide guard, the
two-session concurrency race, waive, and CaseAlreadyOpen (partial unique index).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)
from tests.conftest import set_switch


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _company(db, phone="+998900000001", tax="123456789"):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415

    account = make_account(db, phone)
    company = company_service.create_company(db, account, "UZ", tax)
    return account, company


def _submit(db, monkeypatch, phone="+998900000001", tax="123456789"):  # noqa: ANN001, ANN202
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    account, company = _company(db, phone, tax)
    verification_service.open_case(db, company)
    monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
    case = verification_service.submit_case(db, company, account)
    return account, company, case


def _set_automated(db, case_id, status) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckType  # noqa: PLC0415

    checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all()
    for check in checks:
        if check.check_type != VerificationCheckType.manual_kyb:
            check.status = status
    db.flush()


# ── open / submit ─────────────────────────────────────────────────────────────


@requires_real_db
def test_open_case_only_for_draft_or_rejected(sf) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with sf() as db:
        _account, company = _company(db)
        case = verification_service.open_case(db, company)
        assert case.status.value == "draft"
        db.commit()

        # second open → CaseAlreadyOpen (ux_open_case partial unique index)
        with pytest.raises(verification_service.CaseAlreadyOpen):
            verification_service.open_case(db, company)
        db.rollback()

        # not openable for a verified company
        company.status = CompanyStatus.verified
        db.commit()
        with pytest.raises(verification_service.CaseNotOpenable):
            verification_service.open_case(db, company)


@requires_real_db
def test_submit_case_spawns_checks_and_transitions_company(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    with sf() as db:
        _account, company, case = _submit(db, monkeypatch)
        db.commit()

        assert case.status == VerificationCaseStatus.checks_running
        assert company.status == CompanyStatus.pending_verification
        checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id).all()
        assert {c.check_type.value for c in checks} == {
            "tax_id_format",
            "bank_requisites",
            "documents_complete",
            "manual_kyb",
        }
        events = (
            db.query(DomainEvent)
            .filter(
                DomainEvent.event_type == event_types.VERIFICATION_CASE_SUBMITTED,
                DomainEvent.aggregate_id == str(case.id),
            )
            .all()
        )
        assert len(events) == 1


# ── evaluator ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_evaluator_failed_check_moves_to_needs_info(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import VerificationCaseStatus, VerificationCheckStatus  # noqa: PLC0415

    with sf() as db:
        _account, _company, case = _submit(db, monkeypatch)
        _set_automated(db, case.id, VerificationCheckStatus.failed)
        verification_service.on_check_completed(db, case.id)
        db.refresh(case)
        assert case.status == VerificationCaseStatus.needs_info


@requires_real_db
def test_evaluator_pending_check_stays_checks_running(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import VerificationCaseStatus  # noqa: PLC0415

    with sf() as db:
        _account, _company, case = _submit(db, monkeypatch)
        # checks are all still pending → evaluator is a no-op
        verification_service.on_check_completed(db, case.id)
        db.refresh(case)
        assert case.status == VerificationCaseStatus.checks_running


@requires_real_db
def test_evaluator_all_pass_goes_pending_review(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import VerificationCaseStatus, VerificationCheckStatus  # noqa: PLC0415

    with sf() as db:
        _account, _company, case = _submit(db, monkeypatch)
        _set_automated(db, case.id, VerificationCheckStatus.passed)
        verification_service.on_check_completed(db, case.id)
        db.refresh(case)
        assert case.status == VerificationCaseStatus.pending_review


@requires_real_db
def test_evaluator_auto_approve_verifies_company(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        CompanyStatus,
        VerificationCaseStatus,
        VerificationCheckStatus,
    )
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    with sf() as db:
        set_switch(verification_auto_approve=True)
        _account, company, case = _submit(db, monkeypatch)
        _set_automated(db, case.id, VerificationCheckStatus.passed)
        verification_service.on_check_completed(db, case.id)
        db.commit()

        db.refresh(case)
        assert case.status == VerificationCaseStatus.approved
        company = db.get(Company, company.id)
        assert company.status == CompanyStatus.verified
        assert company.verified_at is not None
        assert company.reverification_due_at is not None
        assert (
            db.query(DomainEvent)
            .filter(DomainEvent.event_type == event_types.COMPANY_VERIFIED)
            .count()
            == 1
        )


# ── decisions + concurrency ───────────────────────────────────────────────────


def _case_in_pending_review(db, monkeypatch, phone, tax):  # noqa: ANN001, ANN202
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import VerificationCheckStatus  # noqa: PLC0415

    _account, company, case = _submit(db, monkeypatch, phone, tax)
    _set_automated(db, case.id, VerificationCheckStatus.passed)
    verification_service.on_check_completed(db, case.id)
    db.commit()
    return company, case


@requires_real_db
def test_approve_verifies_company_and_sets_reverification(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415

    with sf() as db:
        company, case = _case_in_pending_review(db, monkeypatch, "+998900000001", "123456789")
        verification_service.approve(db, case, staff_user_id=None, actor={"tg": 555}, note="ok")
        db.commit()  # staff_user_id=None ⇒ Telegram/system actor (no staff FK)

        db.refresh(case)
        assert case.status == VerificationCaseStatus.approved
        company = db.get(Company, company.id)
        assert company.status == CompanyStatus.verified
        delta_days = (company.reverification_due_at - company.verified_at).days
        assert delta_days == 365


@requires_real_db
def test_double_approve_across_sessions_is_idempotent(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415

    with sf() as db:
        staff_id = make_staff(db).id
        _company, case = _case_in_pending_review(db, monkeypatch, "+998900000001", "123456789")
        case_id = case.id

    # session 1 approves and commits
    with sf() as s1:
        case1 = s1.get(VerificationCase, case_id)
        verification_service.approve(s1, case1, staff_user_id=staff_id)
        s1.commit()

    # session 2 (fresh view, still sees pending_review) → AlreadyDecided
    with sf() as s2:
        case2 = s2.get(VerificationCase, case_id)
        with pytest.raises(verification_service.AlreadyDecided):
            verification_service.approve(s2, case2, staff_user_id=staff_id)


@requires_real_db
def test_reject_and_request_info(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415

    with sf() as db:
        staff_id = make_staff(db, "a@example.com").id
        company, case = _case_in_pending_review(db, monkeypatch, "+998900000002", "222222222")
        verification_service.request_info(db, case, staff_user_id=staff_id, note="need bank letter")
        db.refresh(case)
        assert case.status == VerificationCaseStatus.needs_info

    with sf() as db:
        staff_id = make_staff(db, "b@example.com").id
        company, case = _case_in_pending_review(db, monkeypatch, "+998900000003", "333333333")
        verification_service.reject(db, case, staff_user_id=staff_id, note="fake docs")
        db.commit()
        db.refresh(case)
        assert case.status == VerificationCaseStatus.rejected
        assert db.get(Company, company.id).status == CompanyStatus.rejected


# ── declared → confirmed on approval ──────────────────────────────────────────


def _declare_roles(db, company_id, roles) -> None:  # noqa: ANN001
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415

    company_service.set_business_roles(db, db.get(Company, company_id), roles)
    db.flush()


def _role_rows(db, company_id):  # noqa: ANN001, ANN202
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415

    return db.query(CompanyBusinessRole).filter_by(company_id=company_id).all()


@requires_real_db
def test_approve_confirms_declared_roles(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as RoleEnum  # noqa: PLC0415

    with sf() as db:
        staff_id = make_staff(db).id
        company, case = _case_in_pending_review(db, monkeypatch, "+998900000001", "123456789")
        _declare_roles(db, company.id, [RoleEnum.laboratory])
        verification_service.approve(db, case, staff_user_id=staff_id)
        db.commit()

        rows = _role_rows(db, company.id)
        assert [r.status for r in rows] == [BusinessRoleStatus.confirmed]
        assert rows[0].confirmed_by == staff_id


@requires_real_db
def test_auto_approve_confirms_declared_roles(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, VerificationCheckStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as RoleEnum  # noqa: PLC0415
    with sf() as db:
        set_switch(verification_auto_approve=True)
        _account, company, case = _submit(db, monkeypatch)
        _declare_roles(db, company.id, [RoleEnum.distributor, RoleEnum.trader])
        _set_automated(db, case.id, VerificationCheckStatus.passed)
        verification_service.on_check_completed(db, case.id)
        db.commit()

        rows = _role_rows(db, company.id)
        assert {r.status for r in rows} == {BusinessRoleStatus.confirmed}
        assert {r.confirmed_by for r in rows} == {None}  # auto path — no staff actor


@requires_real_db
def test_reject_leaves_roles_declared(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as RoleEnum  # noqa: PLC0415

    with sf() as db:
        staff_id = make_staff(db).id
        company, case = _case_in_pending_review(db, monkeypatch, "+998900000004", "444444444")
        _declare_roles(db, company.id, [RoleEnum.manufacturer])
        verification_service.reject(db, case, staff_user_id=staff_id, note="fake docs")
        db.commit()

        rows = _role_rows(db, company.id)
        assert [r.status for r in rows] == [BusinessRoleStatus.declared]


@requires_real_db
def test_waive_check_requires_reason_and_reevaluates(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        VerificationCaseStatus,
        VerificationCheckStatus,
        VerificationCheckType,
    )

    with sf() as db:
        staff_id = make_staff(db).id
        _account, _company, case = _submit(db, monkeypatch)
        # all automated pass EXCEPT bank_requisites, which we then waive
        checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id).all()
        bank = next(c for c in checks if c.check_type == VerificationCheckType.bank_requisites)
        for check in checks:
            if check.check_type not in {
                VerificationCheckType.manual_kyb,
                VerificationCheckType.bank_requisites,
            }:
                check.status = VerificationCheckStatus.passed
        bank.status = VerificationCheckStatus.failed
        db.flush()

        with pytest.raises(verification_service.WaiveReasonRequired):
            verification_service.waive_check(db, bank, staff_user_id=staff_id, reason="  ")

        verification_service.waive_check(db, bank, staff_user_id=staff_id, reason="letter on file")
        db.refresh(case)
        # bank waived + others passed → evaluator advances the case
        assert case.status == VerificationCaseStatus.pending_review
