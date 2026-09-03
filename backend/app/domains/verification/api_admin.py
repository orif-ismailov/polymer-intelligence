"""Staff verification + company admin API (R1 W5 — T5.4). Under /api/v1/admin.

Analysts/admins work the FIFO verification queue and decide cases; admins waive
checks and suspend/reinstate companies (suspend emits COMPANY_SUSPENDED, whose
consumer archives the company's approved offers). Unlike the portal views, these
expose reviewer identity, presigned documents, and the audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.companies import directory as directory_service
from app.domains.companies import service as company_service
from app.domains.companies.models import Company, CompanyBankAccount
from app.domains.verification import checks as verification_checks
from app.domains.verification import registry as registry_service
from app.domains.verification import service as verification_service
from app.domains.verification.models import (
    VerificationCase,
    VerificationCheck,
    VerificationDocument,
)
from app.domains.verification.registry_models import RegistrySnapshot
from app.integrations import gov_registry
from app.models.enums import CompanyStatus, VerificationCaseStatus, VerificationCheckType
from app.models.staff import AuditLog, StaffUser
from app.services import (
    storage_service,
)

router = APIRouter(prefix="/admin", tags=["admin-verification"])


class _DecisionIn(BaseModel):
    note: str | None = None


class _WaiveIn(BaseModel):
    reason: str


# ── serializers ───────────────────────────────────────────────────────────────


def _company_or_404(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _case_or_404(db: Session, case_id: int) -> VerificationCase:
    case = db.get(VerificationCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _check_row(check: VerificationCheck) -> dict[str, Any]:
    return {
        "id": check.id,
        "check_type": str(check.check_type),
        "status": str(check.status),
        "result": check.result,
        "attempts": check.attempts,
        "last_error": check.last_error,
        "waived_by": check.waived_by,
        "waive_reason": check.waive_reason,
    }


def _case_summary(db: Session, case: VerificationCase) -> dict[str, Any]:
    company = db.get(Company, case.company_id)
    checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id).all()
    return {
        "id": case.id,
        "company_id": case.company_id,
        "company_tax_id": company.tax_id if company else None,
        "company_name": (company.short_name or company.legal_name) if company else None,
        "case_type": str(case.case_type),
        "status": str(case.status),
        "submitted_at": case.submitted_at,
        "checks": {str(c.check_type): str(c.status) for c in checks},
    }


def _company_profile(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "public_id": str(company.public_id),
        "jurisdiction": company.jurisdiction,
        "tax_id": company.tax_id,
        "legal_name": company.legal_name,
        "short_name": company.short_name,
        "legal_form": company.legal_form,
        "legal_address": company.legal_address,
        "director_name": company.director_name,
        "status": str(company.status),
        "verified_at": company.verified_at,
        "reverification_due_at": company.reverification_due_at,
        "roles": [{"role": str(r.role), "status": str(r.status)} for r in company.business_roles],
        # Portal-parity naming (schemas/portal_company.py CompanySummaryOut): a
        # role is "declared" (non-revoked) from registration, "confirmed" only
        # once staff verify the company — same distinction, staff side.
        "declared_roles": directory_service.active_roles(company),
        "confirmed_roles": directory_service.confirmed_roles(company),
        # Raw JSONB, unvalidated — other account types leave these NULL.
        "manufacturer_profile": company.manufacturer_profile,
        "logistics_profile": company.logistics_profile,
        "laboratory_profile": company.laboratory_profile,
    }


# ── verification cases ────────────────────────────────────────────────────────


@router.get("/verification/cases")
def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("verification", "read")),
) -> list[dict[str, Any]]:
    query = db.query(VerificationCase)
    if status_filter:
        try:
            query = query.filter(VerificationCase.status == VerificationCaseStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bad status") from exc
    # FIFO: oldest submissions first (drafts with no submitted_at sort last).
    cases = (
        query.order_by(VerificationCase.submitted_at.asc().nulls_last(), VerificationCase.id.asc())
        .all()
    )
    return [_case_summary(db, c) for c in cases]


@router.get("/verification/cases/{case_id}")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("verification", "read")),
) -> dict[str, Any]:
    case = _case_or_404(db, case_id)
    company = _company_or_404(db, case.company_id)
    checks = db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id).all()
    documents = (
        db.query(VerificationDocument)
        .filter(VerificationDocument.company_id == company.id)
        .order_by(VerificationDocument.id)
        .all()
    )
    banks = db.query(CompanyBankAccount).filter(CompanyBankAccount.company_id == company.id).all()
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity == "verification_cases", AuditLog.entity_id == str(case.id))
        .order_by(AuditLog.id.desc())
        .limit(50)
        .all()
    )
    return {
        "id": case.id,
        "case_type": str(case.case_type),
        "status": str(case.status),
        "submitted_at": case.submitted_at,
        "decided_at": case.decided_at,
        "decided_by": case.decided_by,
        "decision_note": case.decision_note,
        "company": _company_profile(company),
        "bank_accounts": [
            {"id": b.id, "bank_mfo": b.bank_mfo, "account_masked": f"****{b.account_last4}",
             "currency": b.currency, "status": str(b.status)}
            for b in banks
        ],
        "checks": [_check_row(c) for c in checks],
        "documents": [
            {"id": d.id, "kind": str(d.kind), "mime_type": d.mime_type, "size_bytes": d.size_bytes,
             "status": str(d.status), "sha256": d.sha256,
             "download_url": storage_service.presign_verification_document(d, ttl=600)}
            for d in documents
        ],
        "audit": [
            {"id": a.id, "action": a.action, "staff_user_id": a.staff_user_id,
             "details": a.details, "created_at": a.created_at}
            for a in audit
        ],
        # P7.c — the newest snapshot of each kind. Absent kinds are simply not in
        # the map: "never checked" and "checked, found nothing" must not look alike.
        "registry": {
            kind: _snapshot_row(snapshot)
            for kind, snapshot in registry_service.all_latest(db, company.id).items()
        },
    }


def _snapshot_row(snapshot: RegistrySnapshot) -> dict[str, Any]:
    """One registry observation, with a short-lived link to its screenshot."""
    evidence_url = (
        storage_service.presign_object(snapshot.evidence_path, ttl=600)
        if snapshot.evidence_path
        else None
    )
    return {
        "id": snapshot.id,
        "kind": snapshot.kind,
        "source": snapshot.source,
        "provider": snapshot.provider,
        "payload": snapshot.payload,
        "raw_status": snapshot.raw_status,
        "note": snapshot.note,
        "created_by": snapshot.created_by,
        "evidence_url": evidence_url,
        "fetched_at": snapshot.fetched_at,
        "created_at": snapshot.created_at,
    }


@router.post("/verification/cases/{case_id}/registry-check")
def record_registry_check(
    case_id: int,
    kind: str = Form(...),
    # `company` fields
    registry_status: str | None = Form(default=None, alias="status"),
    raw_status: str | None = Form(default=None),
    name: str | None = Form(default=None),
    director: str | None = Form(default=None),
    oked: str | None = Form(default=None),
    address: str | None = Form(default=None),
    # `vat` fields
    registered: bool = Form(default=False),
    certificate_no: str | None = Form(default=None),
    note: str | None = Form(default=None),
    evidence: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("verification", "write")),
) -> dict[str, Any]:
    """Record a registry check an operator performed by hand (P7.c — T5.4).

    The pre-ПЦД bridge, and the half of P7.c that works today: staff read an open
    service (my.soliq.uz for the VAT register, license.gov.uz for licences,
    registr.stat.uz for the company itself), transcribe the result and optionally
    attach a screenshot. INTEGRATIONS.md §3 sanctions exactly this.

    One transaction does all of it: an immutable `registry_snapshots` row with the
    operator's name on it, the derived `VerificationCheck` verdict, a re-evaluation
    of the case, and the audit entry. The verdict comes from the SAME pure function
    that will judge a ПЦД answer — an operator's reading is weighted no differently,
    and the only record of which it was is the snapshot's `source`.

    `require_analyst_or_admin`: this is verification work, not an admin power.
    """
    case = _case_or_404(db, case_id)
    company = _company_or_404(db, case.company_id)

    if kind not in registry_service.SNAPSHOT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_kind"
        )

    payload, effective_raw_status = _manual_payload(
        kind,
        company.tax_id,
        registry_status=registry_status,
        raw_status=raw_status,
        name=name,
        director=director,
        oked=oked,
        address=address,
        registered=registered,
        certificate_no=certificate_no,
    )

    evidence_path: str | None = None
    evidence_sha: str | None = None
    if evidence is not None and evidence.filename:
        content = evidence.file.read()
        try:
            evidence_path, evidence_sha = storage_service.store_registry_evidence(
                company.id, content, evidence.filename
            )
        except ValueError as exc:
            # Refuse BEFORE anything is recorded: a snapshot whose screenshot was
            # rejected would claim evidence it does not have.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    snapshot = registry_service.record_snapshot(
        db,
        company,
        kind=kind,
        source=registry_service.SNAPSHOT_SOURCE_MANUAL,
        provider=registry_service.PROVIDER_MANUAL,
        payload=payload,
        raw_status=effective_raw_status,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha,
        note=note,
        created_by=staff.id,
    )

    check_status: str | None = None
    check_type = _CHECK_FOR_KIND.get(kind)
    if check_type is not None:
        result = _CHECK_FN[check_type](company, snapshot)
        check = verification_service.upsert_check(
            db, case.id, check_type, result.status, result.result
        )
        check_status = str(check.status)

    db.commit()
    db.refresh(case)
    return {
        "snapshot": _snapshot_row(snapshot),
        "check_status": check_status,
        "case_status": str(case.status),
    }


#: Which verification check each snapshot kind feeds. `licenses` has none: a
#: licence is checked against a SUBSTANCE at publication time (P5
#: `company_license_service`), not against a company at onboarding — recording the
#: snapshot is still useful as evidence for that later decision.
_CHECK_FOR_KIND: dict[str, VerificationCheckType] = {
    registry_service.SNAPSHOT_KIND_COMPANY: VerificationCheckType.gov_registry,
    registry_service.SNAPSHOT_KIND_VAT: VerificationCheckType.vat_status,
}

_CHECK_FN = {
    VerificationCheckType.gov_registry: verification_checks.check_gov_registry,
    VerificationCheckType.vat_status: verification_checks.check_vat_status,
}


def _manual_payload(
    kind: str,
    tax_id: str,
    *,
    registry_status: str | None,
    raw_status: str | None,
    name: str | None,
    director: str | None,
    oked: str | None,
    address: str | None,
    registered: bool,
    certificate_no: str | None,
) -> tuple[dict[str, object], str | None]:
    """Build the snapshot payload from the operator's form.

    Routed through the same DTOs the live adapter produces, so a transcription and
    an API answer are byte-comparable in the table — and a future ПЦД adapter
    cannot accidentally introduce a second payload shape.
    """
    if kind == registry_service.SNAPSHOT_KIND_COMPANY:
        record = gov_registry.CompanySnapshot(
            inn=tax_id,
            name=name,
            status=(registry_status or gov_registry.COMPANY_UNKNOWN).strip().lower(),
            raw_status=raw_status,
            director=director,
            oked=oked,
            address=address,
        )
        return record.as_payload(), raw_status
    if kind == registry_service.SNAPSHOT_KIND_VAT:
        vat = gov_registry.VatSnapshot(
            registered=registered, certificate_no=certificate_no, raw_status=raw_status
        )
        return vat.as_payload(), raw_status
    # licenses — free-form for now: the operator's note plus the raw text they saw.
    # Structuring it needs the actual КИС «Лицензия» field set, which we do not have.
    return {"licenses": [], "transcribed": raw_status or ""}, raw_status


#: The statuses a case can never leave. Everything else that refuses a decision is
#: refusing it FOR NOW, which is a different answer — see `_decision_conflict`.
_TERMINAL_CASE_STATUSES = frozenset(
    {
        VerificationCaseStatus.approved,
        VerificationCaseStatus.rejected,
        VerificationCaseStatus.cancelled,
    }
)


def _decision_conflict(db: Session, case: VerificationCase) -> HTTPException:
    """Say WHICH conflict refused the decision, because the two are not alike.

    `_claim_pending_review` updates `WHERE status='pending_review'` and raises on
    rowcount 0, which lumps together two situations a person must tell apart: a
    colleague (or the Telegram button) decided the case a moment ago, and the case
    has not REACHED a decidable state — checks still running, or `needs_info`
    waiting on the applicant. This endpoint used to answer "Case already decided"
    to both, so a case nobody had touched reported itself as handled by someone
    else; that untrue sentence is what made the queue look broken.

    Still a 409 either way — it is a state conflict — but the body now carries a
    code the dashboard can turn into the right screen.
    """
    db.refresh(case)
    terminal = case.status in _TERMINAL_CASE_STATUSES
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "already_decided" if terminal else "not_pending_review",
            "case_status": str(case.status),
        },
    )


def _decide(db: Session, case_id: int, staff_id: int, note: str | None, action: str) -> dict[str, Any]:
    case = _case_or_404(db, case_id)
    fn = {"approve": verification_service.approve, "reject": verification_service.reject,
          "request_info": verification_service.request_info}[action]
    try:
        fn(db, case, staff_user_id=staff_id, actor={"staff": staff_id}, note=note)
    except verification_service.AlreadyDecided as exc:
        raise _decision_conflict(db, case) from exc
    db.commit()
    return _case_summary(db, case)


@router.post("/verification/cases/{case_id}/approve")
def approve_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("verification", "write")),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "approve")


@router.post("/verification/cases/{case_id}/reject")
def reject_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("verification", "write")),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "reject")


@router.post("/verification/cases/{case_id}/request-info")
def request_info_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("verification", "write")),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "request_info")


@router.post("/verification/checks/{check_id}/waive")
def waive_check(
    check_id: int, body: _WaiveIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("verification", "write")),
) -> dict[str, Any]:
    check = db.get(VerificationCheck, check_id)
    if check is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check not found")
    try:
        verification_service.waive_check(db, check, staff_user_id=staff.id, reason=body.reason)
    except verification_service.WaiveReasonRequired as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reason required") from exc
    db.commit()
    return _check_row(check)


# ── companies ─────────────────────────────────────────────────────────────────


@router.get("/companies")
def list_companies(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("companies", "read")),
) -> list[dict[str, Any]]:
    query = db.query(Company)
    if status_filter:
        try:
            query = query.filter(Company.status == CompanyStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bad status") from exc
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Company.tax_id.ilike(like))
            | (Company.legal_name.ilike(like))
            | (Company.short_name.ilike(like))
        )
    companies = query.order_by(Company.created_at.desc()).limit(200).all()
    return [_company_profile(c) for c in companies]


@router.get("/companies/{company_id}")
def get_company(
    company_id: int, db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("companies", "read")),
) -> dict[str, Any]:
    return _company_profile(_company_or_404(db, company_id))


@router.post("/companies/{company_id}/suspend")
def suspend_company(
    company_id: int, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("companies", "write")),
) -> dict[str, Any]:
    company = _company_or_404(db, company_id)
    try:
        company_service.suspend(db, company, staff.id)
    except company_service.InvalidCompanyTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not suspendable") from exc
    db.commit()
    return _company_profile(company)


@router.post("/companies/{company_id}/reinstate")
def reinstate_company(
    company_id: int, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("companies", "write")),
) -> dict[str, Any]:
    company = _company_or_404(db, company_id)
    try:
        company_service.reinstate(db, company, staff.id)
    except company_service.InvalidCompanyTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not reinstatable") from exc
    db.commit()
    return _company_profile(company)
