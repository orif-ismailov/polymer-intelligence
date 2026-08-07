"""Verification case orchestration (R1 W4 — T4.2).

Open a case (one open case per company — enforced by the `ux_open_case` partial
unique index, not an app check), submit it (spawn the four R1 checks + dispatch the
`verify`-queue task), evaluate the completed checks, and let a human (dashboard or
Telegram) decide it. Concurrency follows ARCHITECTURE §6.1:

  * human decisions are OPTIMISTIC — `UPDATE … WHERE status='pending_review'`;
    rowcount 0 ⇒ someone already decided (idempotent no-op for the TG button);
  * the machine evaluator takes `SELECT … FOR UPDATE` on the case so two checks
    finishing at once produce exactly one evaluation;
  * "one open case" is a DB partial unique index.

Approval flips the company to `verified` (+365-day reverification) and emits the
outbox events that later waves turn into notifications.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyBusinessRole
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    VerificationCaseStatus,
    VerificationCaseType,
    VerificationCheckStatus,
    VerificationCheckType,
)
from app.models.verification import VerificationCase, VerificationCheck
from app.services import (
    audit_service,
    company_service,
    event_service,
    event_types,
    settings_service,
)

logger = logging.getLogger(__name__)

_REVERIFICATION_DAYS = 365

#: How many times `run_single_check` may attempt a check before giving up. Declared
#: here rather than in the task because the EVALUATOR needs the same number: an
#: `unavailable` check blocks the case while retries remain and stops blocking once
#: they are exhausted (see `on_check_completed`). Two copies of this number would
#: disagree exactly when a provider is down.
MAX_CHECK_ATTEMPTS = 5

# The four checks R1 spawns for every submitted case.
_R1_CHECK_TYPES: tuple[VerificationCheckType, ...] = (
    VerificationCheckType.tax_id_format,
    VerificationCheckType.bank_requisites,
    VerificationCheckType.documents_complete,
    VerificationCheckType.manual_kyb,
)

#: P7.c registry checks. Spawned at submit ONLY on the live rail — on the stub
#: rail (the shipped default) they are created when an operator records a manual
#: snapshot, so a case never sits waiting for a channel we do not have.
_REGISTRY_CHECK_TYPES: tuple[VerificationCheckType, ...] = (
    VerificationCheckType.gov_registry,
    VerificationCheckType.vat_status,
)

_OPEN_CASE_STATUSES = frozenset(
    VerificationCaseStatus(s)
    for s in VerificationCaseStatus
    if s
    not in {
        VerificationCaseStatus.approved,
        VerificationCaseStatus.rejected,
        VerificationCaseStatus.cancelled,
    }
)


# ── Domain exceptions ─────────────────────────────────────────────────────────


class CaseNotOpenable(Exception):
    """A case can only be opened for a draft/rejected company."""


class CaseAlreadyOpen(Exception):
    """The company already has an open verification case."""


class NoOpenCase(Exception):
    """The company has no open case to submit."""


class CaseNotSubmittable(Exception):
    """The case can't be submitted from its current status."""


class AlreadyDecided(Exception):
    """The case is no longer pending review — someone already decided it."""


class WaiveReasonRequired(Exception):
    """Waiving a check requires a non-empty reason."""


# ── Case lifecycle ────────────────────────────────────────────────────────────


def _open_case_for(db: Session, company_id: int) -> VerificationCase | None:
    return (
        db.query(VerificationCase)
        .filter(
            VerificationCase.company_id == company_id,
            VerificationCase.status.in_(_OPEN_CASE_STATUSES),
        )
        .first()
    )


def open_case(
    db: Session,
    company: Company,
    case_type: VerificationCaseType = VerificationCaseType.onboarding,
) -> VerificationCase:
    """Open a draft verification case for a draft/rejected company (one open at a time)."""
    if company.status not in {CompanyStatus.draft, CompanyStatus.rejected}:
        raise CaseNotOpenable(str(company.status))
    if company.status == CompanyStatus.rejected:
        company_service.transition(
            db, company, CompanyStatus.draft, actor={"via": "reopen_case"}
        )

    case = VerificationCase(
        company_id=company.id, case_type=case_type, status=VerificationCaseStatus.draft
    )
    try:
        with db.begin_nested():  # SAVEPOINT: the ux_open_case partial index is the guard
            db.add(case)
            db.flush()
    except IntegrityError as exc:
        raise CaseAlreadyOpen(str(company.id)) from exc

    audit_service.write_audit(
        db, None, "vercase.open", "verification_cases", str(case.id),
        {"company_id": company.id, "case_type": str(case_type)},
    )
    return case


def submit_case(db: Session, company: Company, account: UserAccount) -> VerificationCase:
    """(Re)spawn the R1 checks, move the case to checks_running, dispatch the verify task."""
    case = _open_case_for(db, company.id)
    if case is None:
        raise NoOpenCase(str(company.id))
    if case.status not in {VerificationCaseStatus.draft, VerificationCaseStatus.needs_info}:
        raise CaseNotSubmittable(str(case.status))

    # Fresh checks each submit (resubmit from needs_info replaces the prior set).
    db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id).delete()
    db.flush()
    for check_type in (*_R1_CHECK_TYPES, *_registry_checks_for(db)):
        db.add(
            VerificationCheck(
                case_id=case.id, check_type=check_type, status=VerificationCheckStatus.pending
            )
        )

    case.status = VerificationCaseStatus.checks_running
    case.submitted_at = company_service.now_utc()
    db.flush()

    if company.status == CompanyStatus.draft:
        company_service.transition(
            db, company, CompanyStatus.pending_verification, actor={"account_id": account.id}
        )

    event_service.emit(
        db, event_types.VERIFICATION_CASE_SUBMITTED, "verification_case", case.id,
        {"company_id": company.id, "account_id": account.id},
    )
    audit_service.write_audit(
        db, None, "vercase.submit", "verification_cases", str(case.id),
        {"account_id": account.id},
    )
    _dispatch_checks(case.id)
    return case


def _registry_checks_for(db: Session) -> tuple[VerificationCheckType, ...]:
    """The registry checks to spawn, given the configured rail.

    Empty on the stub rail, which is what ships: there is no ПЦД channel, so a
    spawned check would only ever be `unavailable`, and a case whose checks can
    never resolve is worse than a case with fewer checks. On the stub rail these
    appear the moment an operator records a manual snapshot (`upsert_check`).
    """
    from app.integrations.gov_registry import MODE_LIVE, current_mode  # noqa: PLC0415

    return _REGISTRY_CHECK_TYPES if current_mode(db) == MODE_LIVE else ()


def upsert_check(
    db: Session,
    case_id: int,
    check_type: VerificationCheckType,
    status: VerificationCheckStatus,
    result: dict[str, object],
) -> VerificationCheck:
    """Create or overwrite one check's outcome, then re-evaluate the case.

    Used by the operator's manual registry check: a check the submit did not
    spawn (stub rail) is created on the spot, and a re-check overwrites its
    predecessor's verdict. The EVIDENCE is not overwritten — that lives in
    `registry_snapshots`, which is append-only. This row is a derived verdict, and
    the case only needs the current one.
    """
    check = (
        db.query(VerificationCheck)
        .filter(
            VerificationCheck.case_id == case_id,
            VerificationCheck.check_type == check_type,
        )
        .first()
    )
    if check is None:
        # `attempts` has a Python-side default that only applies at flush, so a
        # freshly constructed row carries None until then — set it here.
        check = VerificationCheck(case_id=case_id, check_type=check_type, attempts=0)
        db.add(check)
    check.status = status
    check.result = result
    check.attempts += 1
    check.finished_at = company_service.now_utc()
    db.flush()

    event_service.emit(
        db,
        event_types.VERIFICATION_CHECK_COMPLETED,
        "verification_check",
        check.id,
        {"case_id": case_id, "check_status": str(status)},
    )
    on_check_completed(db, case_id)
    return check


def _dispatch_checks(case_id: int) -> None:
    """Enqueue run_verification_checks on the verify queue (fail-soft)."""
    try:
        from app.tasks.verification import run_verification_checks  # noqa: PLC0415

        run_verification_checks.apply_async(args=[case_id], queue="verify", retry=False)
    except Exception as exc:  # noqa: BLE001 — broker outage must not break submit
        logger.warning("verification.dispatch_failed", extra={"case_id": case_id, "error": str(exc)})


# ── Evaluator (machine — FOR UPDATE) ──────────────────────────────────────────


def _set_case_status(db: Session, case: VerificationCase, to: VerificationCaseStatus) -> None:
    case.status = to
    db.flush()


def _still_running(check: VerificationCheck) -> bool:
    """True while a check may yet produce a different answer.

    `unavailable` counts as running only while the task has attempts left. Once
    the retry budget is spent the provider is simply absent, and the case must be
    allowed to reach a human — see the note in `on_check_completed`.
    """
    if check.status in {VerificationCheckStatus.pending, VerificationCheckStatus.running}:
        return True
    return (
        check.status == VerificationCheckStatus.unavailable
        and check.attempts < MAX_CHECK_ATTEMPTS
    )


def on_check_completed(db: Session, case_id: int) -> VerificationCase | None:
    """Re-evaluate a case after a check finishes (or a waive). Idempotent under FOR UPDATE.

    Any automated check failed → needs_info. All automated checks resolved
    ({passed, warning, waived}) → auto-approve (if enabled) else pending_review.
    Otherwise (a check still pending/running, or `unavailable` with retries left)
    → stay checks_running. manual_kyb is a human item and does NOT block
    pending_review.

    **`unavailable` stops blocking once retries are exhausted** (P7.c T5.2). It
    used to block unconditionally, which meant a check that failed all five
    attempts pinned the case in `checks_running` — where `approve()` cannot reach
    it, because the human decisions are optimistic updates against
    `pending_review`. A dead provider therefore disabled the manual path it was
    supposed to leave open, contradicting the R1 degradation invariant. R1 shipped
    safely only because none of its four checks could go `unavailable`; the P7.c
    registry checks can, and legitimately do.
    """
    case = db.execute(
        select(VerificationCase).where(VerificationCase.id == case_id).with_for_update()
    ).scalar_one_or_none()
    if case is None or case.status not in {
        VerificationCaseStatus.checks_running,
        VerificationCaseStatus.needs_info,
    }:
        return case  # already decided, or not in an evaluatable state

    checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all()
    automated = [c for c in checks if c.check_type != VerificationCheckType.manual_kyb]

    if any(_still_running(c) for c in automated):
        return case  # not finished yet

    if any(c.status == VerificationCheckStatus.failed for c in automated):
        _set_case_status(db, case, VerificationCaseStatus.needs_info)
        event_service.emit(
            db, event_types.VERIFICATION_CASE_NEEDS_INFO, "verification_case", case.id,
            {"company_id": case.company_id},
        )
        return case

    if settings_service.get(db, "verification_auto_approve"):
        now = company_service.now_utc()
        case.status = VerificationCaseStatus.approved
        case.decided_at = now
        case.decision_note = "auto-approved"
        db.flush()
        _finalize_approval(db, case, staff_user_id=None, actor={"via": "auto"}, note="auto-approved")
        return case

    _set_case_status(db, case, VerificationCaseStatus.pending_review)
    return case


# ── Decisions (human — optimistic) ────────────────────────────────────────────


def _load_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:  # pragma: no cover — FK guarantees it exists
        raise CompanyMissing(str(company_id))
    return company


class CompanyMissing(Exception):
    """Invariant violation: a case points at a missing company."""


def _resolve_manual_kyb(
    db: Session, case_id: int, status: VerificationCheckStatus, staff_user_id: int | None
) -> None:
    db.execute(
        update(VerificationCheck)
        .where(
            VerificationCheck.case_id == case_id,
            VerificationCheck.check_type == VerificationCheckType.manual_kyb,
            VerificationCheck.status == VerificationCheckStatus.pending,
        )
        .values(status=status, waived_by=staff_user_id)
    )


def _finalize_approval(
    db: Session,
    case: VerificationCase,
    *,
    staff_user_id: int | None,
    actor: dict[str, object] | None,
    note: str | None,
) -> None:
    """Company-verified side effects of an approval (case row already set to approved)."""
    now = company_service.now_utc()
    company = _load_company(db, case.company_id)
    company.verified_at = now
    company.reverification_due_at = now + datetime.timedelta(days=_REVERIFICATION_DAYS)
    company_service.transition(
        db, company, CompanyStatus.verified, staff_user_id=staff_user_id, actor=actor
    )
    # Verification vouches for what the company registered as: its declared
    # business roles become confirmed here — the ONLY app-code writer of
    # `confirmed` (the confirmed-gated surfaces — pools, directories, badges —
    # all key off this transition). Auto-approve has no staff actor, so
    # `confirmed_by` stays NULL on that path.
    db.execute(
        update(CompanyBusinessRole)
        .where(
            CompanyBusinessRole.company_id == company.id,
            CompanyBusinessRole.status == BusinessRoleStatus.declared,
        )
        .values(status=BusinessRoleStatus.confirmed, confirmed_by=staff_user_id)
    )
    _resolve_manual_kyb(db, case.id, VerificationCheckStatus.passed, staff_user_id)
    event_service.emit(
        db, event_types.VERIFICATION_CASE_APPROVED, "verification_case", case.id,
        {"company_id": company.id},
    )
    event_service.emit(
        db, event_types.COMPANY_VERIFIED, "company", company.id, {"case_id": case.id}
    )
    audit_service.write_audit(
        db, staff_user_id, "vercase.approve", "verification_cases", str(case.id),
        _audit_details(actor, note),
    )
    db.flush()


def _audit_details(actor: dict[str, object] | None, note: str | None) -> dict[str, object]:
    details: dict[str, object] = dict(actor or {})
    if note is not None:
        details["note"] = note
    return details


def _claim_pending_review(db: Session, case: VerificationCase, values: dict[str, object]) -> None:
    """Optimistically move a case OUT of pending_review; AlreadyDecided if it already left.

    The `WHERE status='pending_review'` guard + row lock make the decision exactly-once:
    a second concurrent decider updates 0 rows and gets AlreadyDecided (idempotent for
    the Telegram button that may be pressed twice).
    """
    result = db.execute(
        update(VerificationCase)
        .where(
            VerificationCase.id == case.id,
            VerificationCase.status == VerificationCaseStatus.pending_review,
        )
        .values(values)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]  # DML → CursorResult.rowcount
        raise AlreadyDecided(str(case.id))
    db.refresh(case)


def approve(
    db: Session,
    case: VerificationCase,
    *,
    staff_user_id: int | None = None,
    actor: dict[str, object] | None = None,
    note: str | None = None,
) -> VerificationCase:
    """Approve a pending-review case → company verified. Idempotent (AlreadyDecided)."""
    now = company_service.now_utc()
    _claim_pending_review(
        db, case,
        {
            "status": VerificationCaseStatus.approved,
            "decided_at": now,
            "decided_by": staff_user_id,
            "decision_note": note,
        },
    )
    _finalize_approval(db, case, staff_user_id=staff_user_id, actor=actor, note=note)
    return case


def reject(
    db: Session,
    case: VerificationCase,
    *,
    staff_user_id: int | None = None,
    actor: dict[str, object] | None = None,
    note: str | None = None,
) -> VerificationCase:
    """Reject a pending-review case → company rejected. Idempotent (AlreadyDecided)."""
    now = company_service.now_utc()
    _claim_pending_review(
        db, case,
        {
            "status": VerificationCaseStatus.rejected,
            "decided_at": now,
            "decided_by": staff_user_id,
            "decision_note": note,
        },
    )
    company = _load_company(db, case.company_id)
    company_service.transition(
        db, company, CompanyStatus.rejected, staff_user_id=staff_user_id, actor=actor
    )
    event_service.emit(
        db, event_types.VERIFICATION_CASE_REJECTED, "verification_case", case.id,
        {"company_id": company.id},
    )
    audit_service.write_audit(
        db, staff_user_id, "vercase.reject", "verification_cases", str(case.id),
        _audit_details(actor, note),
    )
    db.flush()
    return case


def request_info(
    db: Session,
    case: VerificationCase,
    *,
    staff_user_id: int | None = None,
    actor: dict[str, object] | None = None,
    note: str | None = None,
) -> VerificationCase:
    """Send a pending-review case back to needs_info. Idempotent (AlreadyDecided)."""
    _claim_pending_review(
        db, case,
        {"status": VerificationCaseStatus.needs_info, "decision_note": note},
    )
    event_service.emit(
        db, event_types.VERIFICATION_CASE_NEEDS_INFO, "verification_case", case.id,
        {"company_id": case.company_id},
    )
    audit_service.write_audit(
        db, staff_user_id, "vercase.request_info", "verification_cases", str(case.id),
        _audit_details(actor, note),
    )
    db.flush()
    return case


def waive_check(
    db: Session, check: VerificationCheck, *, staff_user_id: int, reason: str
) -> VerificationCheck:
    """Waive a check (reason required), then re-run the evaluator for its case."""
    if not reason or not reason.strip():
        raise WaiveReasonRequired(str(check.id))
    check.status = VerificationCheckStatus.waived
    check.waived_by = staff_user_id
    check.waive_reason = reason
    db.flush()
    audit_service.write_audit(
        db, staff_user_id, "vercheck.waive", "verification_checks", str(check.id),
        {"reason": reason, "check_type": str(check.check_type)},
    )
    on_check_completed(db, check.case_id)
    return check
