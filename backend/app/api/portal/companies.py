"""Portal company + verification endpoints (R1 W5 — T5.1). Under /api/v1/portal.

All routes require a portal account (`get_current_account`); company-scoped routes
resolve membership via `company_service.get_company_for` (non-member → 404, never
revealing existence). Domain exceptions map to typed HTTP errors. Views are
client-safe: bank numbers masked, verification checks show status + human
requirements only (no reviewer identity or internals).
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, rate_limited, require_company_admin
from app.core.db import get_db
from app.core.redis import get_redis
from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyBankAccount
from app.models.enums import (
    BankAccountStatus,
    CompanyBusinessRole,
    DocumentReviewStatus,
    VerificationDocumentKind,
)
from app.models.verification import VerificationCase, VerificationCheck, VerificationDocument
from app.schemas.portal_company import (
    BankAccountIn,
    BankAccountOut,
    BusinessRoleOut,
    CaseOut,
    CheckOut,
    CompanyCreateIn,
    CompanyDetailOut,
    CompanyMediaOut,
    CompanyProfileUpdateIn,
    CompanyReviewIn,
    CompanyReviewOut,
    CompanySummaryOut,
    DocumentOut,
    PublicProfileUpdateIn,
    RolesUpdateIn,
)
from app.services import (
    audit_service,
    company_service,
    directory_service,
    rate_limit,
    review_service,
    storage_service,
    verification_service,
)

router = APIRouter(prefix="/portal/companies", tags=["portal-companies"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _check_out(check: VerificationCheck) -> CheckOut:
    # check.result is user-safe by construction (missing kinds, reasons, masked last4).
    return CheckOut(check_type=str(check.check_type), status=str(check.status), detail=check.result)


def _case_out(db: Session, case: VerificationCase | None) -> CaseOut | None:
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


def _latest_case(db: Session, company_id: int) -> VerificationCase | None:
    return (
        db.query(VerificationCase)
        .filter(VerificationCase.company_id == company_id)
        .order_by(VerificationCase.id.desc())
        .first()
    )


def _summary_out(db: Session, company: Company) -> CompanySummaryOut:
    active = verification_service._open_case_for(db, company.id)
    return CompanySummaryOut(
        id=company.id,
        public_id=company.public_id,
        jurisdiction=company.jurisdiction,
        tax_id=company.tax_id,
        legal_name=company.legal_name,
        short_name=company.short_name,
        status=str(company.status),
        verified_at=company.verified_at,
        logo_url=storage_service.presign_company_logo(company),
        cover_url=storage_service.presign_company_cover(company),
        confirmed_roles=directory_service.confirmed_roles(company),
        declared_roles=directory_service.active_roles(company),
        active_case=_case_out(db, active),
    )


def _detail_out(db: Session, company: Company) -> CompanyDetailOut:
    banks = (
        db.query(CompanyBankAccount)
        .filter(
            CompanyBankAccount.company_id == company.id,
            CompanyBankAccount.status != BankAccountStatus.archived,
        )
        .all()
    )
    documents = (
        db.query(VerificationDocument)
        .filter(VerificationDocument.company_id == company.id)
        .order_by(VerificationDocument.id)
        .all()
    )
    return CompanyDetailOut(
        id=company.id,
        public_id=company.public_id,
        jurisdiction=company.jurisdiction,
        tax_id=company.tax_id,
        legal_name=company.legal_name,
        short_name=company.short_name,
        legal_form=company.legal_form,
        legal_address=company.legal_address,
        actual_address=company.actual_address,
        registration_number=company.registration_number,
        director_name=company.director_name,
        registration_date=company.registration_date,
        manufacturer_profile=company.manufacturer_profile,
        logistics_profile=company.logistics_profile,
        laboratory_profile=company.laboratory_profile,
        status=str(company.status),
        identity_locked=company.identity_locked,
        verified_at=company.verified_at,
        reverification_due_at=company.reverification_due_at,
        logo_url=storage_service.presign_company_logo(company),
        cover_url=storage_service.presign_company_cover(company),
        roles=[BusinessRoleOut(role=str(r.role), status=str(r.status)) for r in company.business_roles],
        bank_accounts=[
            BankAccountOut(
                id=b.id,
                bank_mfo=b.bank_mfo,
                bank_name=b.bank_name,
                account_masked=f"****{b.account_last4}",
                currency=b.currency,
                status=str(b.status),
            )
            for b in banks
        ],
        documents=[
            DocumentOut(
                id=d.id,
                kind=str(d.kind),
                mime_type=d.mime_type,
                size_bytes=d.size_bytes,
                status=str(d.status),
                created_at=d.created_at,
            )
            for d in documents
        ],
        case=_case_out(db, _latest_case(db, company.id)),
    )


# ── company CRUD ──────────────────────────────────────────────────────────────


@router.post("", response_model=CompanySummaryOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> CompanySummaryOut:
    # Validate BEFORE enforcing the quota: `enforce_daily` increments unconditionally,
    # so charging it for input we are about to reject meant five STIR typos locked a
    # legitimate applicant out of registering for the rest of the UTC day.
    try:
        jurisdiction, tax_id = company_service.normalize_new_company(body.jurisdiction, body.tax_id)
    except company_service.InvalidTaxId as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except company_service.InvalidJurisdiction as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    try:
        rate_limit.enforce_daily(
            redis_client, "company_create", account.id, rate_limit.COMPANY_CREATE_PER_DAY
        )
    except rate_limit.RateLimited as exc:
        raise rate_limited(exc) from exc
    try:
        company = company_service.create_company(db, account, jurisdiction, tax_id)
        verification_service.open_case(db, company)  # auto-open a draft case
    except company_service.CompanyAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company already registered") from exc
    db.commit()
    return _summary_out(db, company)


@router.get("", response_model=list[CompanySummaryOut])
def list_companies(
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[CompanySummaryOut]:
    return [_summary_out(db, c) for c in company_service.list_my_companies(db, account)]


@router.get("/{company_id}", response_model=CompanyDetailOut)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    return _detail_out(db, company_or_404(db, account, company_id))


@router.patch("/{company_id}", response_model=CompanyDetailOut)
def update_company(
    company_id: int,
    body: CompanyProfileUpdateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    company = company_or_404(db, account, company_id)
    try:
        company_service.update_profile(db, company, account, **body.model_dump(exclude_none=True))
    except company_service.ProfileNotEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile not editable now") from exc
    except company_service.IdentityLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="identity_locked"
        ) from exc
    db.commit()
    return _detail_out(db, company)


@router.patch("/{company_id}/public-profile", response_model=CompanyDetailOut)
def update_public_profile(
    company_id: int,
    body: PublicProfileUpdateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    """PATCH /portal/companies/{id}/public-profile — storefront copy, post-verification.

    Deliberately NOT part of `PATCH /{company_id}`: that route is gated on the
    company still being editable (`draft`, or a case still undecided), and a
    carrier only reaches a public directory once it is `verified` — the one state
    that gate refuses. See `company_service.update_public_profile` for why the
    answer is a narrower door rather than a wider gate.

    Owner/manager only: this is the text on the company's public page.
    """
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)
    company_service.update_public_profile(
        db,
        company,
        account,
        # `exclude_unset`: an absent key means "leave it alone", not "clear it".
        logistics=(
            body.logistics.model_dump(exclude_unset=True) if body.logistics else None
        ),
        laboratory=(
            body.laboratory.model_dump(exclude_unset=True) if body.laboratory else None
        ),
    )
    db.commit()
    return _detail_out(db, company)


@router.post(
    "/{company_id}/reviews",
    response_model=CompanyReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_review(
    company_id: int,
    body: CompanyReviewIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyReviewOut:
    """POST /portal/companies/{id}/reviews — rate a counterparty.

    A portal write, not a public one: `tests/test_public_api.py` asserts no route
    on the anonymous router takes an account, and a review that anyone could post
    without one would be a spam surface rather than a signal.

    Re-submitting replaces the author company's existing review — a review is a
    standing opinion per counterparty, so the second one is an edit, not a
    duplicate the UI would have to explain.
    """
    author = company_or_404(db, account, body.company_id)
    try:
        subject = review_service.get_reviewable_company(db, company_id)
    except review_service.ReviewSubjectNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    try:
        review = review_service.upsert_review(
            db,
            subject=subject,
            author=author,
            account=account,
            rating=body.rating,
            body=body.body,
        )
    except review_service.SelfReview as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="self_review"
        ) from exc

    db.commit()
    db.refresh(review)
    return CompanyReviewOut(
        id=review.id,
        company_id=review.company_id,
        author_company_id=review.author_company_id,
        rating=review.rating,
        body=review.body,
        status=str(review.status),
        created_at=review.created_at,
    )


@router.put("/{company_id}/roles", response_model=CompanyDetailOut)
def set_roles(
    company_id: int,
    body: RolesUpdateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    company = company_or_404(db, account, company_id)
    try:
        roles = [CompanyBusinessRole(r) for r in body.roles]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown role") from exc
    try:
        company_service.set_business_roles(db, company, roles)
    except company_service.InvalidBusinessRoles as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="roles_span_multiple_account_types",
        ) from exc
    db.commit()
    return _detail_out(db, company)


# ── bank accounts ─────────────────────────────────────────────────────────────


@router.post("/{company_id}/bank-accounts", response_model=CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def add_bank_account(
    company_id: int,
    body: BankAccountIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    company = company_or_404(db, account, company_id)
    try:
        company_service.add_bank_account(
            db, company, body.bank_mfo, body.account_number,
            bank_name=body.bank_name, currency=body.currency,
        )
    except company_service.InvalidBankMfo as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _detail_out(db, company)


@router.delete("/{company_id}/bank-accounts/{account_id}", response_model=CompanyDetailOut)
def archive_bank_account(
    company_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    company = company_or_404(db, account, company_id)
    bank = (
        db.query(CompanyBankAccount)
        .filter(CompanyBankAccount.id == account_id, CompanyBankAccount.company_id == company.id)
        .first()
    )
    if bank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    bank.status = BankAccountStatus.archived
    db.commit()
    return _detail_out(db, company)


# ── documents ─────────────────────────────────────────────────────────────────


# ── Company logo (P1 W1 — T1.3) ───────────────────────────────────────────────


@router.post(
    "/{company_id}/logo",
    response_model=CompanyDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload or replace the company logo",
)
async def upload_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    """JPEG/PNG ≤ 5 MB (FR-M1). Replacing deletes the previous object."""
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)

    content = await file.read()
    try:
        key = storage_service.upload_company_logo(db, company, content, file.filename or "logo")
    except ValueError as exc:
        # `file_too_large` / `invalid_file_type` — typed, so the portal can localise.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    audit_service.write_audit(
        db,
        None,
        "company.logo_upload",
        "company",
        str(company.id),
        {"actor_account_id": account.id, "key": key},
    )
    db.commit()
    return _detail_out(db, company)


@router.delete(
    "/{company_id}/logo",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the company logo",
)
def delete_logo(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Idempotent — removing an absent logo is a 204, not a 404."""
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)

    had_logo = bool(company.logo_storage_path)
    storage_service.delete_company_logo(db, company)
    if had_logo:
        audit_service.write_audit(
            db, None, "company.logo_delete", "company", str(company.id),
            {"actor_account_id": account.id},
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{company_id}/cover",
    response_model=CompanyDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload or replace the company cover image",
)
async def upload_cover(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyDetailOut:
    """JPEG/PNG ≤ 8 MB. Replacing deletes the previous object.

    Available to a VERIFIED company, unlike the profile PATCH: a cover is brand
    material, not a requisite anyone checked — the same reasoning as
    `PATCH /public-profile`.
    """
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)

    content = await file.read()
    try:
        key = storage_service.upload_company_cover(db, company, content, file.filename or "cover")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    audit_service.write_audit(
        db, None, "company.cover_upload", "company", str(company.id),
        {"actor_account_id": account.id, "key": key},
    )
    db.commit()
    return _detail_out(db, company)


@router.delete(
    "/{company_id}/cover",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the company cover image",
)
def delete_cover(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Idempotent — removing an absent cover is a 204, not a 404."""
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)

    storage_service.delete_company_cover(db, company)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{company_id}/media",
    response_model=CompanyMediaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one company image (capability thumbnails)",
)
async def upload_media(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyMediaOut:
    """Returns the media id + its URL; the caller stores the reference itself.

    For carriers that reference is `logistics_profile.capability_images`, keyed by
    capability — so the JSONB stays the ordering authority and a reorder cannot
    orphan a row.
    """
    company = company_or_404(db, account, company_id)
    require_company_admin(db, account, company_id)

    content = await file.read()
    try:
        media = storage_service.upload_company_media(
            db, company, content, file.filename or "image"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(media)
    return CompanyMediaOut(
        id=media.id,
        url=storage_service.company_media_url(company.id, media.id),
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
    )


@router.post("/{company_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    company_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> DocumentOut:
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
    content = await file.read()
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


def _document_or_404(db: Session, company_id: int, document_id: int) -> VerificationDocument:
    document = (
        db.query(VerificationDocument)
        .filter(VerificationDocument.id == document_id, VerificationDocument.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


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
    out = _case_out(db, case)
    assert out is not None
    return out


@router.get("/{company_id}/verification", response_model=CaseOut)
def get_verification(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CaseOut:
    company = company_or_404(db, account, company_id)
    out = _case_out(db, _latest_case(db, company.id))
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No verification case")
    return out
