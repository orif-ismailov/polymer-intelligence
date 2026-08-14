"""Applicant-side verification endpoints. Under /api/v1/portal.

Extracted from `app/api/portal/companies.py`, which straddled two domains: company
profile CRUD (companies) and the verification case an applicant submits and watches
(here). Same `/portal/companies` prefix and the same paths as before the split — this
router is mounted alongside the companies router in `app/main.py`.

Route order is not load-bearing across the two routers: every path here sits one
segment deeper than the companies router's `/{company_id}` param route
(`/{company_id}/documents…`, `/{company_id}/verification…`), so neither can shadow
the other.

`case_out` and `latest_case` are public because they are an imported surface —
`app/api/portal/companies.py` embeds a case in its company views, and
`app/api/portal/eimzo.py` renders the case an E-IMZO confirmation just advanced.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, rate_limited
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.verification import service as verification_service
from app.domains.verification.models import (
    VerificationCase,
    VerificationCheck,
    VerificationDocument,
)
from app.domains.verification.schemas import CaseOut, CheckOut, DocumentOut
from app.models.enums import DocumentReviewStatus, VerificationDocumentKind
from app.services import rate_limit, storage_service

router = APIRouter(prefix="/portal/companies", tags=["portal-verification"])


# ── serializers ───────────────────────────────────────────────────────────────


def _check_out(check: VerificationCheck) -> CheckOut:
    # check.result is user-safe by construction (missing kinds, reasons, masked last4).
    return CheckOut(check_type=str(check.check_type), status=str(check.status), detail=check.result)


def case_out(db: Session, case: VerificationCase | None) -> CaseOut | None:
    if case is None:
        return None
    checks = (
        db.query(VerificationCheck)
        .filter(VerificationCheck.case_id == case.id)
        .order_by(VerificationCheck.id)
        .all()
    )
    return CaseOut(
        id=case.id,
        case_type=str(case.case_type),
        status=str(case.status),
        submitted_at=case.submitted_at,
        checks=[_check_out(c) for c in checks],
    )


def latest_case(db: Session, company_id: int) -> VerificationCase | None:
    return (
        db.query(VerificationCase)
        .filter(VerificationCase.company_id == company_id)
        .order_by(VerificationCase.id.desc())
        .first()
    )


def _document_or_404(db: Session, company_id: int, document_id: int) -> VerificationDocument:
    document = (
        db.query(VerificationDocument)
        .filter(VerificationDocument.id == document_id, VerificationDocument.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


# ── documents ─────────────────────────────────────────────────────────────────


@router.post("/{company_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    company_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DocumentOut:
    """Attach a verification document to a company.

    Sync `def` on purpose: the body is a Redis rate-limit round-trip, a blocking
    boto3 PUT and a commit. As `async def` those ran on the event loop and stalled
    every other request in the process. `file.file` is the underlying
    SpooledTemporaryFile, so no `await` is needed to read it.
    """
    company = company_or_404(db, account, company_id)
    try:
        rate_limit.enforce_daily(
            redis_client, "doc_upload", account.id, rate_limit.DOCUMENT_UPLOAD_PER_DAY
        )
    except rate_limit.RateLimited as exc:
        raise rate_limited(exc) from exc
    try:
        doc_kind = VerificationDocumentKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown document kind") from exc
    content = file.file.read()
    try:
        document = storage_service.upload_verification_document(
            db, company, account.id, doc_kind, content, file.filename or "upload"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return DocumentOut(
        id=document.id, kind=str(document.kind), mime_type=document.mime_type,
        size_bytes=document.size_bytes, status=str(document.status), created_at=document.created_at,
    )


@router.get("/{company_id}/documents/{document_id}/download")
def download_document(
    company_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RedirectResponse:
    company = company_or_404(db, account, company_id)
    document = _document_or_404(db, company.id, document_id)
    url = storage_service.presign_verification_document(document, ttl=600)
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.delete("/{company_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    company_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> None:
    company = company_or_404(db, account, company_id)
    document = _document_or_404(db, company.id, document_id)
    if document.status != DocumentReviewStatus.pending_review:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document already reviewed")
    db.delete(document)
    db.commit()


# ── verification ──────────────────────────────────────────────────────────────


@router.post("/{company_id}/verification/submit", response_model=CaseOut)
def submit_verification(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CaseOut:
    company = company_or_404(db, account, company_id)
    try:
        case = verification_service.submit_case(db, company, account)
    except verification_service.NoOpenCase as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No open case") from exc
    except verification_service.CaseNotSubmittable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case not submittable") from exc
    db.commit()
    out = case_out(db, case)
    if out is None:  # pragma: no cover — submit_case always yields a case
        raise RuntimeError("case_out returned None for a just-submitted case")
    return out


@router.get("/{company_id}/verification", response_model=CaseOut)
def get_verification(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CaseOut:
    company = company_or_404(db, account, company_id)
    out = case_out(db, latest_case(db, company.id))
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No verification case")
    return out
