"""Portal company-offer endpoints (R1 W5 — T5.2). Under /api/v1/portal.

A verified company publishes offers that flow through the EXISTING moderation
machine (pending_moderation → approved/rejected). All routes require a portal
account + company membership (non-member → 404). Publishing from an unverified
company → 403 with a typed `{code: "company_not_verified"}` body.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.companies import _company_or_404
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.enums import OfferFileKind, SellerOfferStatus
from app.models.marketplace import SellerOffer
from app.schemas.portal_company import CompanyOfferIn, CompanyOfferOut
from app.services import offer_service, storage_service

router = APIRouter(prefix="/portal/companies", tags=["portal-offers"])


def _offer_or_404(db: Session, company_id: int, offer_id: int) -> SellerOffer:
    offer = (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.company_id == company_id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.get("/{company_id}/offers", response_model=list[CompanyOfferOut])
def list_offers(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[SellerOffer]:
    company = _company_or_404(db, account, company_id)
    return offer_service.list_company_offers(db, company.id)


@router.post("/{company_id}/offers", response_model=CompanyOfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(
    company_id: int,
    body: CompanyOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = _company_or_404(db, account, company_id)
    try:
        offer = offer_service.create_company_offer(db, company, account, body)
    except offer_service.CompanyNotVerified as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "company_not_verified"}
        ) from exc
    db.commit()
    offer_service.enqueue_offer_group_notify(offer.id)
    return offer


@router.get("/{company_id}/offers/{offer_id}", response_model=CompanyOfferOut)
def get_offer(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = _company_or_404(db, account, company_id)
    return _offer_or_404(db, company.id, offer_id)


@router.patch("/{company_id}/offers/{offer_id}", response_model=CompanyOfferOut)
def update_offer(
    company_id: int,
    offer_id: int,
    body: CompanyOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = _company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    offer, requeued = offer_service.update_company_offer(db, offer, body)
    db.commit()
    if requeued:
        offer_service.enqueue_offer_group_notify(offer.id, edited=True)
    return offer


@router.post("/{company_id}/offers/{offer_id}/archive", response_model=CompanyOfferOut)
def archive_offer(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = _company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    offer.status = SellerOfferStatus.archived
    offer.published_at = None
    db.commit()
    return offer


@router.post("/{company_id}/offers/{offer_id}/files", response_model=CompanyOfferOut, status_code=status.HTTP_201_CREATED)
async def upload_offer_file(
    company_id: int,
    offer_id: int,
    kind: str = Form("image"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = _company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    try:
        file_kind = OfferFileKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown file kind") from exc
    content = await file.read()
    try:
        storage_service.upload_offer_file(db, offer.id, content, file.filename or "upload", file_kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return offer
