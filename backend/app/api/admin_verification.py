"""Staff verification + company admin API (R1 W5 — T5.4). Under /api/v1/admin.

Analysts/admins work the FIFO verification queue and decide cases; admins waive
checks and suspend/reinstate companies (suspend emits COMPANY_SUSPENDED, whose
consumer archives the company's approved offers). Unlike the portal views, these
expose reviewer identity, presigned documents, and the audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_analyst_or_admin
from app.core.db import get_db
from app.models.companies import Company, CompanyBankAccount
from app.models.enums import CompanyStatus, VerificationCaseStatus
from app.models.staff import AuditLog, StaffUser
from app.models.verification import VerificationCase, VerificationCheck, VerificationDocument
from app.services import company_service, storage_service, verification_service

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
    }


# ── verification cases ────────────────────────────────────────────────────────


@router.get("/verification/cases")
def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
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
    _staff: StaffUser = Depends(require_analyst_or_admin),
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
    }


def _decide(db: Session, case_id: int, staff_id: int, note: str | None, action: str) -> dict[str, Any]:
    case = _case_or_404(db, case_id)
    fn = {"approve": verification_service.approve, "reject": verification_service.reject,
          "request_info": verification_service.request_info}[action]
    try:
        fn(db, case, staff_user_id=staff_id, actor={"staff": staff_id}, note=note)
    except verification_service.AlreadyDecided as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case already decided") from exc
    db.commit()
    return _case_summary(db, case)


@router.post("/verification/cases/{case_id}/approve")
def approve_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "approve")


@router.post("/verification/cases/{case_id}/reject")
def reject_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "reject")


@router.post("/verification/cases/{case_id}/request-info")
def request_info_case(
    case_id: int, body: _DecisionIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, Any]:
    return _decide(db, case_id, staff.id, body.note, "request_info")


@router.post("/verification/checks/{check_id}/waive")
def waive_check(
    check_id: int, body: _WaiveIn, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
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
    _staff: StaffUser = Depends(require_analyst_or_admin),
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
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, Any]:
    return _company_profile(_company_or_404(db, company_id))


@router.post("/companies/{company_id}/suspend")
def suspend_company(
    company_id: int, db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
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
    staff: StaffUser = Depends(require_admin),
) -> dict[str, Any]:
    company = _company_or_404(db, company_id)
    try:
        company_service.reinstate(db, company, staff.id)
    except company_service.InvalidCompanyTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not reinstatable") from exc
    db.commit()
    return _company_profile(company)
