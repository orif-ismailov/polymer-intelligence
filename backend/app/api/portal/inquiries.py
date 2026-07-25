"""Portal per-offer inquiry endpoints (R2 W3 T3.2). Under /api/v1/portal.

A buyer, acting on behalf of a selected company, sends an inquiry against an
approved offer; it enters the EXISTING staff moderation queue. The buyer sees
only the buyer-facing view (``OfferRequestOut``) — moderation internals stay
hidden, exactly as in the Mini App. Editing a submitted inquiry re-enters
moderation (mirror of the webapp semantics).

Company-scoped: every read/write carries ``company_id`` and membership is enforced
(``get_company_for`` → 404 for non-members = no cross-company disclosure).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.companies import _company_or_404
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.enums import OfferRequestStatus, SellerOfferStatus
from app.models.marketplace import OfferRequest, SellerOffer
from app.schemas.marketplace import OfferRequestOut
from app.schemas.portal_market import PortalInquiryCreate, PortalInquiryUpdate
from app.services import offer_request_service

router = APIRouter(prefix="/portal", tags=["portal-inquiries"])


def _is_member(db: Session, account: UserAccount, company_id: int | None) -> bool:
    """True when the account is an active member of company_id (None → False)."""
    if company_id is None:
        return False
    from app.services import company_service  # noqa: PLC0415

    try:
        company_service.get_company_for(db, account, company_id)
        return True
    except company_service.CompanyNotFound:
        return False


@router.post(
    "/market/{offer_id}/inquiries",
    response_model=OfferRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send an inquiry on an offer (as a company)",
)
def create_inquiry(
    offer_id: int,
    body: PortalInquiryCreate,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> OfferRequestOut:
    """POST /portal/market/{offer_id}/inquiries — pending inquiry → staff moderation."""
    company = _company_or_404(db, account, body.company_id)
    offer = (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.status == SellerOfferStatus.approved)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    try:
        req = offer_request_service.create_company_inquiry(db, company, account, offer, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    offer_request_service.enqueue_offer_request_to_group(req.id)
    return OfferRequestOut.model_validate(req)


@router.get(
    "/inquiries",
    response_model=list[OfferRequestOut],
    summary="Inquiries my company has sent",
)
def list_sent(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[OfferRequestOut]:
    company = _company_or_404(db, account, company_id)
    rows = offer_request_service.list_for_company(db, company.id)
    return [OfferRequestOut.model_validate(r) for r in rows]


@router.get(
    "/inquiries/incoming",
    response_model=list[OfferRequestOut],
    summary="Approved inquiries received on my company's offers",
)
def list_incoming(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[OfferRequestOut]:
    company = _company_or_404(db, account, company_id)
    rows = offer_request_service.list_incoming_for_company(db, company.id)
    return [OfferRequestOut.model_validate(r) for r in rows]


def _inquiry_or_404(db: Session, inquiry_id: int) -> OfferRequest:
    req = offer_request_service.get_offer_request(db, inquiry_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    return req


@router.get(
    "/inquiries/{inquiry_id}",
    response_model=OfferRequestOut,
    summary="One inquiry (sender or, if approved, the offer owner)",
)
def get_inquiry(
    inquiry_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> OfferRequestOut:
    req = _inquiry_or_404(db, inquiry_id)
    is_sender = _is_member(db, account, req.company_id)
    # The offer owner may view an inquiry only once it is approved (post-moderation).
    is_owner = (
        req.status == OfferRequestStatus.approved
        and _is_member(db, account, req.offer.company_id)
    )
    if not (is_sender or is_owner):
        # Opaque 404 — no cross-company disclosure.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    return OfferRequestOut.model_validate(req)


@router.patch(
    "/inquiries/{inquiry_id}",
    response_model=OfferRequestOut,
    summary="Revise a sent inquiry (re-enters moderation)",
)
def update_inquiry(
    inquiry_id: int,
    body: PortalInquiryUpdate,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> OfferRequestOut:
    _company_or_404(db, account, body.company_id)
    req = _inquiry_or_404(db, inquiry_id)
    # Only the sending company may edit its own inquiry.
    if req.company_id != body.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    try:
        req, _changes = offer_request_service.update_offer_request(db, req, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return OfferRequestOut.model_validate(req)
