"""verify-queue task tests (R1 W4 — T4.4).

DB-free: task registration + verify-queue routing. Guarded (test_polymer): the
full submit → run_single_check → evaluator → pending_review pipeline, and the
provider-error → unavailable + retry path (eager mode).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

# ── registration / routing (DB-free) ──────────────────────────────────────────


def test_verification_module_listed_in_task_modules() -> None:
    from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

    assert "app.tasks.verification" in _TASK_MODULES


def test_verification_tasks_registered() -> None:
    import app.tasks.verification  # noqa: F401, PLC0415
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert {"run_verification_checks", "run_single_check"} <= set(celery_app.tasks)


def test_verification_tasks_route_to_verify_queue() -> None:
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_routes["app.tasks.verification.*"] == {"queue": "verify"}


# ── pipeline (real DB) ─────────────────────────────────────────────────────────


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
def test_run_single_check_pipeline_reaches_pending_review(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies import service as company_service
    from app.domains.verification import service as verification_service
    from app.domains.verification.models import (
        VerificationCase,
        VerificationCheck,
        VerificationDocument,
    )
    from app.models.enums import (  # noqa: PLC0415
        VerificationCaseStatus,
        VerificationDocumentKind,
    )
    from tests._verification_db import make_account

    monkeypatch.setattr("app.core.db.SessionLocal", sf)

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        # a registration certificate so documents_complete passes (no bank → warning is OK)
        db.add(
            VerificationDocument(
                company_id=company.id,
                kind=VerificationDocumentKind.registration_certificate,
                storage_path="verification/x",
                sha256="z",
                uploaded_by_user_account_id=account.id,
            )
        )
        verification_service.open_case(db, company)
        monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
        case = verification_service.submit_case(db, company, account)
        db.commit()
        case_id = case.id
        check_ids = [
            c.id for c in db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id)
        ]

    from app.tasks.verification import run_single_check  # noqa: PLC0415

    for check_id in check_ids:
        run_single_check.apply(args=[check_id]).get()

    with sf() as db:
        case = db.get(VerificationCase, case_id)
        assert case.status == VerificationCaseStatus.pending_review


@requires_real_db
def test_run_single_check_marks_unavailable_and_retries_on_error(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies import service as company_service
    from app.domains.verification import service as verification_service
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus, VerificationCheckType  # noqa: PLC0415
    from tests._verification_db import make_account

    monkeypatch.setattr("app.core.db.SessionLocal", sf)

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        verification_service.open_case(db, company)
        monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
        case = verification_service.submit_case(db, company, account)
        db.commit()
        tax_check_id = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case.id,
                VerificationCheck.check_type == VerificationCheckType.tax_id_format,
            )
            .one()
            .id
        )

    # Force the check function to raise → the task must mark it unavailable + retry.
    monkeypatch.setattr(
        "app.tasks.verification._run_check",
        lambda db, check: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    from app.tasks.verification import run_single_check  # noqa: PLC0415

    result = run_single_check.apply(args=[tax_check_id])
    assert result.failed()  # retries exhausted → task fails

    with sf() as db:
        check = db.get(VerificationCheck, tax_check_id)
        assert check.status == VerificationCheckStatus.unavailable
        assert check.attempts >= 1
        assert check.last_error is not None
