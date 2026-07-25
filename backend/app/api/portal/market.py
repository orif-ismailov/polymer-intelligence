"""Portal market (read) endpoints (R2 W3 T3.1). Under /api/v1/portal.

Twin of the webapp market surface for portal accounts: browse approved offers and
open a single offer with the caller company's own inquiries on it. Reuses the
shared ``offer_service`` catalog query + the ``CatalogOfferOut`` serializer so the
card shape stays byte-parity with the Mini App (pinned by a contract test).

All routes require a portal account. The single-offer "my relationship" block is
company-scoped: pass ``company_id`` (membership enforced → 404 for non-members).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.companies import _company_or_404
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.enums import OfferAvailability
from app.schemas.marketplace import CatalogOfferOut, OfferRequestOut
from app.schemas.portal_market import PortalMarketOfferDetail
from app.services import offer_request_service, offer_service

router = APIRouter(prefix="/portal/market", tags=["portal-market"])


@router.get("", response_model=list[CatalogOfferOut], summary="Browse approved offers")
def list_market(
    product_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    availability: OfferAvailability | None = Query(default=None),
    country: str | None = Query(default=None, max_length=2),
    company_id: int | None = Query(
        default=None, description="Exclude this company's own offers when browsing"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[CatalogOfferOut]:
    """GET /portal/market — approved offers with optional filters + pagination.

    When ``company_id`` is a company the caller belongs to, that company's own
    offers are excluded (it cannot inquire on itself).
    """
    exclude_company_id: int | None = None
    if company_id is not None:
        exclude_company_id = _company_or_404(db, account, company_id).id
    offers = offer_service.list_catalog(
        db,
        product_id=product_id,
        q=q,
        availability=availability,
        country=country,
        exclude_company_id=exclude_company_id,
        limit=limit,
        offset=offset,
    )
    return [CatalogOfferOut.model_validate(o) for o in offers]


@router.get(
    "/{offer_id}",
    response_model=PortalMarketOfferDetail,
    summary="Offer detail + my company's inquiries on it",
)
def get_market_offer(
    offer_id: int,
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> PortalMarketOfferDetail:
    """GET /portal/market/{id} — a single approved offer, or 404.

    When ``company_id`` (a company the caller belongs to) is supplied, the response
    includes that company's own inquiries against this offer and sets ``is_own``.
    """
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    out = PortalMarketOfferDetail.model_validate(offer)
    if company_id is not None:
        company = _company_or_404(db, account, company_id)
        out.is_own = offer.company_id is not None and offer.company_id == company.id
        out.my_inquiries = [
            OfferRequestOut.model_validate(i)
            for i in offer_request_service.list_company_inquiries_for_offer(
                db, company.id, offer_id
            )
        ]
    return out
