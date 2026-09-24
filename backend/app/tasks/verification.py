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


def _dispatch_single(check_id: int) -> None:
    """Enqueue one check on the verify queue (fail-soft). The single enqueue point,
    so the dependency below can be exercised without a broker."""
    try:
        run_single_check.apply_async(args=[check_id], queue="verify", retry=False)
    except Exception as exc:  # noqa: BLE001 — broker outage must not crash the caller
        logger.warning(
            "verification.single_check_dispatch_failed",
            extra={"check_id": check_id, "error": str(exc)},
        )


def _registry_pending(db: Any, case_id: int) -> bool:  # noqa: ANN401
    """Whether this case's `gov_registry` check has yet to give its verdict."""
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus, VerificationCheckType

    return bool(
        db.query(VerificationCheck)
        .filter(
            VerificationCheck.case_id == case_id,
            VerificationCheck.check_type == VerificationCheckType.gov_registry,
            VerificationCheck.status.in_(
                (VerificationCheckStatus.pending, VerificationCheckStatus.running)
            ),
        )
        .count()
        > 0
    )


def _release_deferred_documents(db: Any, case_id: int) -> list[int]:  # noqa: ANN401
    """The `documents_complete` checks held back for the registry verdict.

    Returned rather than dispatched: the caller enqueues them only AFTER its own
    commit, or the documents task could read the registry check before its verdict
    is visible and fail on the very certificate the verdict waives.
    """
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus, VerificationCheckType

    return [
        c.id
        for c in db.query(VerificationCheck)
        .filter(
            VerificationCheck.case_id == case_id,
            VerificationCheck.check_type == VerificationCheckType.documents_complete,
            VerificationCheck.status == VerificationCheckStatus.pending,
        )
        .all()
    ]


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
        registry_passed = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == check.case_id,
                VerificationCheck.check_type == VerificationCheckType.gov_registry,
                VerificationCheck.status == VerificationCheckStatus.passed,
            )
            .count()
            > 0
        )
        return verification_checks.check_documents_complete(
            company,
            documents,
            roles,
            has_bank_account=has_bank,
            eimzo_passed=eimzo_passed,
            registry_passed=registry_passed,
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
    """Run one verification check, record its result, and re-evaluate the case.

    Two things beyond "run it and record it", both introduced when the registry
    checks started running on the Didox rail:

    * **A returned `unavailable` is retried like a raised one.** The registry
      checks do not raise when the provider is down — `fetch_and_record` returns
      None and `check_gov_registry` answers `unavailable`, deliberately, so an
      outage is never mistaken for a finding. But that answer used to be recorded
      once and never retried, and the evaluator treats `unavailable` with attempts
      left as still running — so one Didox blip at submit pinned the case in
      `checks_running` for good. It now retries on the same budget and backoff as a
      provider exception, and is only recorded as final once that budget is spent.
    * **A settled registry verdict releases the documents check** that
      `run_verification_checks` held back for it — on a pass, a fail, or retries
      exhausted alike, because every one of those is a verdict the documents check
      can be judged against.
    """
    from sqlalchemy.exc import OperationalError

    from app.core.db import SessionLocal
    from app.domains.verification import service as verification_service
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus, VerificationCheckType
    from app.services import event_service, event_types

    release: list[int] = []
    try:
        with SessionLocal() as db:
            check = db.get(VerificationCheck, check_id)
            if check is None:
                return {"status": "error", "error": "check_not_found"}

            check.status = VerificationCheckStatus.running
            check.started_at = company_service.now_utc()
            check.attempts += 1
            db.flush()
            exhausted = check.attempts >= MAX_CHECK_ATTEMPTS
            is_registry = check.check_type == VerificationCheckType.gov_registry

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
                if exhausted:
                    # The budget is spent, so this is the verdict. Evaluate now —
                    # nothing else will, if this was the case's last open check.
                    verification_service.on_check_completed(db, check.case_id)
                    if is_registry:
                        release = _release_deferred_documents(db, check.case_id)
                db.commit()
                for held in release:
                    _dispatch_single(held)
                logger.warning(
                    "verification.check_unavailable",
                    extra={"check_id": check_id, "attempts": check.attempts, "error": str(exc)},
                )
                raise self.retry(countdown=60 * check.attempts, exc=exc) from exc

            check.status = result.status
            check.result = result.result
            check.finished_at = company_service.now_utc()

            if result.status == VerificationCheckStatus.unavailable and not exhausted:
                # Not an answer yet — see the docstring. No completion event, no
                # evaluation: the check has not completed.
                reason = (result.result or {}).get("reason")
                check.last_error = str(reason) if reason else "unavailable"
                db.commit()
                raise self.retry(countdown=60 * check.attempts)

            if result.status != VerificationCheckStatus.unavailable:
                # An answer arrived, so the previous attempt's error no longer
                # describes this check. Left in place it read on the case page as
                # «Последняя ошибка: no_snapshot» under a verdict that had been
                # reached — "answered" and "failed" on one row. A FINAL
                # `unavailable` (retries exhausted) keeps it: that error is the
                # reason there is no answer.
                check.last_error = None

            db.flush()
            event_service.emit(
                db, event_types.VERIFICATION_CHECK_COMPLETED, "verification_check", check.id,
                {"case_id": check.case_id, "check_status": str(result.status)},
            )
            verification_service.on_check_completed(db, check.case_id)
            if is_registry:
                release = _release_deferred_documents(db, check.case_id)
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

    # After the commit, so the documents task sees this verdict (see
    # `_release_deferred_documents`).
    for held in release:
        _dispatch_single(held)
    return {"status": "ok", "check_status": str(result.status)}


@celery_app.task(name="run_verification_checks")  # type: ignore[untyped-decorator]
def run_verification_checks(case_id: int) -> dict[str, Any]:
    """Dispatch run_single_check for every pending check of a case (verify queue).

    Everything fans out in parallel EXCEPT `documents_complete` while the case has
    a `gov_registry` check still to answer. The registry verdict can waive the
    registration certificate, so judging the documents first would fail them —
    and a failed automated check sends the case to `needs_info` and asks the
    applicant for a certificate the next check was about to waive. The held check
    is released by `run_single_check` once the registry has a verdict.
    """
    from app.core.db import SessionLocal
    from app.domains.verification.models import VerificationCheck
    from app.models.enums import VerificationCheckStatus, VerificationCheckType

    with SessionLocal() as db:
        pending = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case_id,
                VerificationCheck.status == VerificationCheckStatus.pending,
            )
            .all()
        )
        hold = _registry_pending(db, case_id)
        check_ids = [
            c.id
            for c in pending
            if not (hold and c.check_type == VerificationCheckType.documents_complete)
        ]

    for check_id in check_ids:
        _dispatch_single(check_id)

    return {"dispatched": len(check_ids), "pending": len(pending)}


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
