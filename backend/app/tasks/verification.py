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

from app.domains.companies import service as company_service
from app.domains.verification.checks import CheckResult
from app.domains.verification.service import MAX_CHECK_ATTEMPTS
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

#: Backoff for a deadlock/serialization retry. Deliberately short: unlike a dead
#: provider (`60 * attempts`) this is same-instant contention between two checks of
#: one case, and the loser just needs to come back after the winner commits.
_CONTENTION_RETRY_SECONDS = 2


def _run_check(db: Any, check: Any) -> CheckResult:  # noqa: ANN401 — task-layer glue
    """Execute the pure check function for `check`, gathering its inputs from the DB."""
    from app.domains.companies.models import Company, CompanyBankAccount, CompanyBusinessRole
    from app.domains.verification import checks as verification_checks
    from app.domains.verification.models import (
        VerificationCase,
        VerificationCheck,
        VerificationDocument,
    )
    from app.models.enums import VerificationCheckStatus, VerificationCheckType

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

    # P7.c — the two registry checks. Both read the newest snapshot and nothing
    # else, so a live ПЦД answer and an operator's transcription are judged by the
    # same code; only the snapshot's `source` distinguishes them. `fetch_and_record`
    # is attempted first and returns None when there is no channel, which leaves
    # the check `unavailable` rather than manufacturing a finding.
    if check_type in {
        VerificationCheckType.gov_registry,
        VerificationCheckType.vat_status,
    }:
        from app.domains.verification import registry as registry_service
        from app.domains.verification.registry_models import (
            SNAPSHOT_KIND_COMPANY,
            SNAPSHOT_KIND_VAT,
        )

        kind = (
            SNAPSHOT_KIND_COMPANY
            if check_type == VerificationCheckType.gov_registry
            else SNAPSHOT_KIND_VAT
        )
        snapshot = registry_service.fetch_and_record(db, company, kind) or registry_service.latest(
            db, company.id, kind
        )
        if check_type == VerificationCheckType.gov_registry:
            return verification_checks.check_gov_registry(company, snapshot)
        return verification_checks.check_vat_status(company, snapshot)

    raise ValueError(f"unknown check type: {check_type}")


@celery_app.task(  # type: ignore[untyped-decorator]
    name="run_single_check",
    bind=True,
    # One number, one place: the EVALUATOR uses the same budget to decide when an
    # `unavailable` check stops blocking a case (verification_service.MAX_CHECK_ATTEMPTS).
    max_retries=MAX_CHECK_ATTEMPTS,
)
def run_single_check(self: Any, check_id: int) -> dict[str, Any]:  # bound Celery task
    """Run one verification check, record its result, and re-evaluate the case."""
    from sqlalchemy.exc import OperationalError

    from app.core.db import SessionLocal
    from app.domains.verification import service as verification_service
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus
    from app.services import event_service, event_types

    try:
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
            except OperationalError:
                # Transient DB contention, not a provider fault — let the outer
                # handler retry it instead of libelling the provider `unavailable`.
                raise
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
    except OperationalError as exc:
        # `on_check_completed` takes `SELECT … FOR UPDATE` on the SHARED parent
        # `verification_cases` row, so two checks of the same case can deadlock.
        # This used to sit outside every retry guard: the task died "raised
        # unexpected", the rollback reverted even `attempts += 1`, and the check
        # returned to a pristine `pending` that nothing ever re-dispatched — the
        # case stayed in `checks_running` for good and the applicant watched
        # «Идёт проверка» forever. Deadlocks are transient by definition; retry.
        logger.warning(
            "verification.check_contention_retry",
            extra={"check_id": check_id, "error": str(exc)},
        )
        raise self.retry(countdown=_CONTENTION_RETRY_SECONDS, exc=exc) from exc

    return {"status": "ok", "check_status": str(result.status)}


@celery_app.task(name="run_verification_checks")  # type: ignore[untyped-decorator]
def run_verification_checks(case_id: int) -> dict[str, Any]:
    """Dispatch run_single_check for every pending check of a case (verify queue)."""
    from app.core.db import SessionLocal
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus

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
    from app.domains.marketplace.models import SellerOffer
    from app.models.enums import SellerOfferStatus

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
