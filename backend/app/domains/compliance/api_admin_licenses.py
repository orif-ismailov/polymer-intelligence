"""
Staff licence registry (P5 W3 — T3.2).

A company uploads its licence through the existing R1 verification-document
flow; staff read it, accept the document, and register the licence here. That
registration is what a publish gate can act on — the document alone says
nothing about which of the four regimes it covers.

Analysts may read (they answer "why is this offer blocked?"); registering and
revoking are admin acts, because they decide what a company may sell.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.compliance import licenses as company_license_service
from app.domains.compliance.schemas import CompanyLicenseIn, CompanyLicenseOut, LicenseRevokeIn
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin", tags=["compliance"])


def _company_or_404(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.get(
    "/companies/{company_id}/licenses",
    response_model=list[CompanyLicenseOut],
    summary="Licences a company holds (including revoked/expired)",
)
def list_licenses(
    company_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("companies", "read")),
) -> list[CompanyLicenseOut]:
    _company_or_404(db, company_id)
    return company_license_service.list_for(db, company_id)  # type: ignore[return-value]


@router.post(
    "/companies/{company_id}/licenses",
    response_model=CompanyLicenseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a licence",
)
def register_license(
    company_id: int,
    body: CompanyLicenseIn,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("companies", "write")),
) -> CompanyLicenseOut:
    _company_or_404(db, company_id)
    licence = company_license_service.register(
        db,
        company_id=company_id,
        regime=body.regime,
        category=body.category,
        license_number=body.license_number,
        issued_by=body.issued_by,
        issued_at=body.issued_at,
        expires_at=body.expires_at,
        document_id=body.document_id,
        note=body.note,
        staff_user_id=user.id,
    )
    db.commit()
    return licence  # type: ignore[return-value]


@router.post(
    "/licenses/{license_id}/revoke",
    response_model=CompanyLicenseOut,
    summary="Revoke a licence (takes effect immediately)",
)
def revoke_license(
    license_id: int,
    body: LicenseRevokeIn,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("companies", "write")),
) -> CompanyLicenseOut:
    licence = company_license_service.get(db, license_id)
    if licence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    company_license_service.revoke(db, licence, reason=body.reason, staff_user_id=user.id)
    db.commit()
    return licence  # type: ignore[return-value]
