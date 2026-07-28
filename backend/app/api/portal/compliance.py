"""Portal compliance views (P5 W3 — T3.4). Under /api/v1/portal.

Read-only, company-scoped: what an offer still needs before it can be published,
and which licences the company holds. Both are what the "почему не публикуется"
panel is built from — a seller who cannot see the requirement can only guess.

Non-members get 404 (never 403), consistent with the rest of the portal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.companies import _company_or_404
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.marketplace import SellerOffer
from app.schemas.compliance import CompanyLicenseOut, ComplianceOut
from app.services import company_license_service, offer_compliance_service

router = APIRouter(prefix="/portal/companies", tags=["portal-compliance"])


@router.get(
    "/{company_id}/licenses",
    response_model=list[CompanyLicenseOut],
    summary="Licences this company holds",
)
def my_licenses(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[CompanyLicenseOut]:
    """Read-only: licences are registered by staff from an accepted document."""
    company = _company_or_404(db, account, company_id)
    return company_license_service.list_for(db, company.id)  # type: ignore[return-value]


@router.get(
    "/{company_id}/offers/{offer_id}/compliance",
    response_model=ComplianceOut,
    summary="What this offer still needs to be published",
)
def offer_compliance(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ComplianceOut:
    company = _company_or_404(db, account, company_id)
    offer = (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.company_id == company.id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer_compliance_service.verdict_out(db, offer)
