"""Verification check tasks (R1 W4 — T4.4). Queue: verify.

`run_verification_checks(case_id)` fans out one `run_single_check(check_id)` per
pending check. `run_single_check` sets the check running, executes its pure
function, records the result, emits VERIFICATION_CHECK_COMPLETED, and re-runs the
evaluator. Provider errors mark the check `unavailable` and retry with a linear
backoff (`60 * attempts`, max 5) — R1's checks never go unavailable, but the retry
path is load-bearing for the P2/R3 gov/bank/E-IMZO providers, so it ships now.

These run on the isolated `verify` queue (routed in celery_app.py) so a slow
provider can't starve ingest/parse/notify.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import company_service
from app.services.verification_checks import CheckResult
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_check(db: Any, check: Any) -> CheckResult:  # noqa: ANN401 — task-layer glue
    """Execute the pure check function for `check`, gathering its inputs from the DB."""
    from app.models.companies import Company, CompanyBankAccount, CompanyBusinessRole
    from app.models.enums import VerificationCheckStatus, VerificationCheckType
    from app.models.verification import VerificationCase, VerificationCheck, VerificationDocument
    from app.services import verification_checks

    case = db.get(VerificationCase, check.case_id)
    company = db.get(Company, case.company_id)
    check_type = check.check_type

    if check_type == VerificationCheckType.tax_id_format:
        return verification_checks.check_tax_id_format(company)

    if check_type == VerificationCheckType.bank_requisites:
        accounts = (
            db.query(CompanyBankAccount)
            .filter(CompanyBankAccount.company_id == company.id)
            .all()
        )
        return verification_checks.check_bank_requisites(company, accounts)

    if check_type == VerificationCheckType.documents_complete:
        documents = (
            db.query(VerificationDocument)
            .filter(VerificationDocument.company_id == company.id)
            .all()
        )
        roles = [
            r.role
            for r in db.query(CompanyBusinessRole)
            .filter(CompanyBusinessRole.company_id == company.id)
            .all()
        ]
        has_bank = (
            db.query(CompanyBankAccount)
            .filter(CompanyBankAccount.company_id == company.id)
            .count()
            > 0
        )
        eimzo_passed = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == check.case_id,
                VerificationCheck.check_type == VerificationCheckType.eimzo_signature,
                VerificationCheck.status == VerificationCheckStatus.passed,
            )
            .count()
            > 0
        )
        return verification_checks.check_documents_complete(
            company, documents, roles, has_bank_account=has_bank, eimzo_passed=eimzo_passed
        )

    if check_type == VerificationCheckType.manual_kyb:
        return verification_checks.check_manual_kyb()

    raise ValueError(f"unknown check type: {check_type}")


@celery_app.task(name="run_single_check", bind=True, max_retries=5)  # type: ignore[untyped-decorator]
def run_single_check(self: Any, check_id: int) -> dict[str, Any]:  # bound Celery task
    """Run one verification check, record its result, and re-evaluate the case."""
    from app.core.db import SessionLocal
    from app.models.enums import VerificationCheckStatus
    from app.models.verification import VerificationCheck
    from app.services import event_service, event_types, verification_service

    with SessionLocal() as db:
        check = db.get(VerificationCheck, check_id)
        if check is None:
            return {"status": "error", "error": "check_not_found"}

        check.status = VerificationCheckStatus.running
        check.started_at = company_service.now_utc()
        check.attempts += 1
        db.flush()

        try:
            result = _run_check(db, check)
        except Exception as exc:  # noqa: BLE001 — provider failure → unavailable + retry
            check.status = VerificationCheckStatus.unavailable
            check.last_error = str(exc)
            check.finished_at = company_service.now_utc()
            db.commit()
            logger.warning(
                "verification.check_unavailable",
                extra={"check_id": check_id, "attempts": check.attempts, "error": str(exc)},
            )
            raise self.retry(countdown=60 * check.attempts, exc=exc) from exc

        check.status = result.status
        check.result = result.result
        check.finished_at = company_service.now_utc()
        db.flush()
        event_service.emit(
            db, event_types.VERIFICATION_CHECK_COMPLETED, "verification_check", check.id,
            {"case_id": check.case_id, "check_status": str(result.status)},
        )
        verification_service.on_check_completed(db, check.case_id)
        db.commit()

    return {"status": "ok", "check_status": str(result.status)}


@celery_app.task(name="run_verification_checks")  # type: ignore[untyped-decorator]
def run_verification_checks(case_id: int) -> dict[str, Any]:
    """Dispatch run_single_check for every pending check of a case (verify queue)."""
    from app.core.db import SessionLocal
    from app.models.enums import VerificationCheckStatus
    from app.models.verification import VerificationCheck

    with SessionLocal() as db:
        check_ids = [
            c.id
            for c in db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case_id,
                VerificationCheck.status == VerificationCheckStatus.pending,
            )
            .all()
        ]

    dispatched = 0
    for check_id in check_ids:
        try:
            run_single_check.apply_async(args=[check_id], queue="verify", retry=False)
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 — broker outage must not crash the fan-out
            logger.warning(
                "verification.single_check_dispatch_failed",
                extra={"check_id": check_id, "error": str(exc)},
            )

    return {"dispatched": dispatched, "pending": len(check_ids)}


@celery_app.task(name="archive_company_offers")  # type: ignore[untyped-decorator]
def archive_company_offers(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """COMPANY_SUSPENDED consumer: archive a suspended company's approved offers.

    Uniform consumer signature (event_id, aggregate_id, payload). aggregate_id is the
    company id; payload carries it too. Idempotent — an already-archived offer is not
    matched by the WHERE clause.
    """
    from sqlalchemy import update

    from app.core.db import SessionLocal
    from app.models.enums import SellerOfferStatus
    from app.models.marketplace import SellerOffer

    company_id = (payload or {}).get("company_id") or (int(aggregate_id) if aggregate_id else None)
    if company_id is None:
        return {"archived": 0}

    with SessionLocal() as db:
        result = db.execute(
            update(SellerOffer)
            .where(
                SellerOffer.company_id == company_id,
                SellerOffer.status == SellerOfferStatus.approved,
            )
            .values(status=SellerOfferStatus.archived, published_at=None)
        )
        archived = result.rowcount  # type: ignore[attr-defined]
        db.commit()

    logger.info("verification.offers_archived", extra={"company_id": company_id, "count": archived})
    return {"archived": archived}


# Register the COMPANY_SUSPENDED → archive-offers consumer (idempotent; see events.py).
def _register_consumers() -> None:
    from app.services import event_types
    from app.tasks.events import CONSUMERS

    if archive_company_offers not in CONSUMERS.get(event_types.COMPANY_SUSPENDED, []):
        CONSUMERS[event_types.COMPANY_SUSPENDED].append(archive_company_offers)


_register_consumers()
