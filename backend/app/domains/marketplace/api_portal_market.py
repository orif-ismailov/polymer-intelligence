"""Portal market (read) endpoints (R2 W3 T3.1). Under /api/v1/portal.

Twin of the webapp market surface for portal accounts: browse approved offers and
open a single offer with the caller company's own inquiries on it. Reuses the
shared ``offer_service`` catalog query + the ``CatalogOfferOut`` serializer so the
card shape stays byte-parity with the Mini App (pinned by a contract test).

All routes require a portal account. The single-offer "my relationship" block is
company-scoped: pass ``company_id`` (membership enforced → 404 for non-members).
"""

from __future__ import annotations

import decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.companies.models import Company
from app.domains.deals import rfq as rfq_response_service
from app.domains.deals.models import RfqResponse
from app.domains.marketplace import requests as offer_request_service
from app.domains.marketplace import service as offer_service
from app.domains.marketplace.models import SellerOffer
from app.domains.marketplace.portal_market_schemas import (
    MarketRequestListOut,
    MarketRequestOut,
    PortalMarketOfferDetail,
    PortalMarketOfferOut,
    PublicCompanyProfileOut,
)
from app.domains.marketplace.schemas import OfferRequestOut
from app.domains.reference.models import Product
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    OfferAvailability,
    RfqResponseStatus,
    SellerOfferStatus,
)
from app.services import storage_service

router = APIRouter(prefix="/portal/market", tags=["portal-market"])


def _cards(
    db: Session, account: UserAccount, offers: list[object]
) -> list[PortalMarketOfferOut]:
    """Serialize a page of offers, resolving this account's stars in ONE query.

    Per-card lookups would be an N+1 on the busiest screen in the portal.
    """
    cards = [PortalMarketOfferOut.model_validate(o) for o in offers]
    starred = offer_service.favorite_offer_ids(db, account.id, [c.id for c in cards])
    for card in cards:
        card.is_favorite = card.id in starred
    return cards


@router.get("", response_model=list[PortalMarketOfferOut], summary="Browse approved offers")
def list_market(
    product_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    availability: OfferAvailability | None = Query(default=None),
    country: str | None = Query(default=None, max_length=2),
    company_id: int | None = Query(
        default=None, description="Exclude this company's own offers when browsing"
    ),
    seller_company_id: int | None = Query(
        default=None, description="Only offers published by this seller company"
    ),
    has_lab_passport: bool = Query(
        default=False, description="Only offers carrying a laboratory passport"
    ),
    lab_verified: bool = Query(
        default=False, description="Only offers analysed through the platform"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[PortalMarketOfferOut]:
    """GET /portal/market — approved offers with optional filters + pagination.

    When ``company_id`` is a company the caller belongs to, that company's own
    offers are excluded (it cannot inquire on itself).

    ``seller_company_id`` is the opposite filter: only that seller's approved
    listings (public profile Products tab / "see all").

    The two laboratory filters (FR-L5) are separate questions and stack: "has an
    analysis" and "we arranged it". Both default to off — an unticked checkbox
    must not filter anything.
    """
    exclude_company_id: int | None = None
    if company_id is not None:
        exclude_company_id = company_or_404(db, account, company_id).id
    offers = offer_service.list_catalog(
        db,
        product_id=product_id,
        q=q,
        availability=availability,
        country=country,
        exclude_company_id=exclude_company_id,
        company_id=seller_company_id,
        has_lab_passport=has_lab_passport,
        lab_verified=lab_verified,
        limit=limit,
        offset=offset,
    )
    return _cards(db, account, list(offers))


# ── Literal paths BEFORE /{offer_id} ──────────────────────────────────────────
#
# Favorites, the supplier RFQ list and the public company profile must all win
# over the parameter route. Same rule the companies router applies to /directory:
# a literal sibling declared first beats /{offer_id}, with no dependency on the
# order routers are included in app/main.py.


@router.get("/requests", response_model=MarketRequestListOut)
def list_market_requests(
    company_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> MarketRequestListOut:
    """Open RFQs this supplier company may answer — trade terms only.

    Buyer contact details are never included: the platform stays the
    intermediary until a deal is open.

    Served by THIS router, not the deals router, even though the data is a deals
    concern: the full path is /portal/market/requests, which `/{offer_id}` below
    would otherwise match. Declared here it is settled by declaration order; on the
    deals router it silently depended on that router being registered first (P5).
    """
    company = company_or_404(db, account, company_id)
    rows = rfq_response_service.list_open_requests(db, company, limit=limit, offset=offset)

    # A tender announced from the CATALOG carries `product_id` and leaves
    # `product_text` NULL — so the card said "—" where the product name belongs,
    # which is the one thing a supplier decides on. Resolve the catalog name for
    # those rows; a free-typed product keeps the buyer's own words.
    catalog = {
        p.id: p.name_ru
        for p in db.query(Product)
        .filter(Product.id.in_([r.product_id for r in rows if r.product_id] or [0]))
        .all()
    }

    mine = {
        r.request_id: r
        for r in db.query(RfqResponse)
        .filter(
            RfqResponse.company_id == company.id,
            RfqResponse.request_id.in_([r.id for r in rows] or [0]),
            RfqResponse.status != RfqResponseStatus.withdrawn,
        )
        .all()
    }
    return MarketRequestListOut(
        items=[
            MarketRequestOut(
                id=r.id,
                product=r.product_text or catalog.get(r.product_id or 0),
                grade=r.grade_text or r.polymer_type,
                volume=r.volume if r.volume is not None else decimal.Decimal(0),
                volume_unit=r.volume_unit,
                incoterms=str(r.incoterms),
                destination_country=r.destination_country,
                port_or_city=r.port_or_city,
                desired_date=r.desired_date,
                validity_days=r.validity_days,
                urgency=str(r.urgency),
                required_docs=list(r.required_docs or []),
                created_at=r.created_at,
                my_response_id=mine[r.id].id if r.id in mine else None,
                my_response_status=str(mine[r.id].status) if r.id in mine else None,
            )
            for r in rows
        ]
    )


@router.get(
    "/favorites",
    response_model=list[PortalMarketOfferOut],
    summary="This account's starred offers",
)
def list_favorites(
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[PortalMarketOfferOut]:
    """A shortlist is personal — it hangs off the account, not the active company."""
    return _cards(db, account, list(offer_service.list_favorites(db, account.id)))


@router.post(
    "/offers/{offer_id}/favorite",
    status_code=status.HTTP_201_CREATED,
    summary="Star an offer",
)
def add_favorite(
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, bool]:
    """Idempotent: starring twice is not an error, it is already starred."""
    if offer_service.get_catalog_offer(db, offer_id) is None:
        # Only the public catalog has hearts; a draft is not there to star.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    offer_service.add_favorite(db, account.id, offer_id)
    db.commit()
    return {"is_favorite": True}


@router.delete(
    "/offers/{offer_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unstar an offer",
)
def remove_favorite(
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Unstarring something that was never starred is a no-op: the caller's intent
    ("this should not be in my list") is already satisfied."""
    offer_service.remove_favorite(db, account.id, offer_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/companies/{company_id}",
    response_model=PublicCompanyProfileOut,
    summary="Public seller company profile",
)
def get_public_company_profile(
    company_id: int,
    offers_limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> PublicCompanyProfileOut:
    """GET /portal/market/companies/{id} — catalog-safe profile of a verified seller.

    Auth is required (same as the rest of the market), but membership is not:
    any portal account may open a verified company's public sheet. Draft /
    pending companies 404 the same way an unpublished offer does — there is
    nothing public to show yet.

    Bank accounts, verification documents and case internals are never returned.
    """
    company = (
        db.query(Company)
        .options(selectinload(Company.business_roles))
        .filter(Company.id == company_id)
        .first()
    )
    if company is None or company.status != CompanyStatus.verified:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    offer_count = (
        db.query(SellerOffer.id)
        .filter(
            SellerOffer.company_id == company.id,
            SellerOffer.status == SellerOfferStatus.approved,
        )
        .count()
    )
    offers = offer_service.list_catalog(
        db, company_id=company.id, limit=offers_limit, offset=0
    )
    return PublicCompanyProfileOut(
        id=company.id,
        public_id=company.public_id,
        legal_name=company.legal_name,
        short_name=company.short_name,
        legal_form=company.legal_form,
        legal_address=company.legal_address,
        jurisdiction=company.jurisdiction,
        registration_date=company.registration_date,
        verified_at=company.verified_at,
        logo_url=storage_service.presign_company_logo(company),
        roles=[
            str(r.role)
            for r in company.business_roles
            if r.status == BusinessRoleStatus.confirmed
        ],
        offer_count=offer_count,
        offers=_cards(db, account, list(offers)),
    )


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
    out.is_favorite = offer.id in offer_service.favorite_offer_ids(db, account.id, [offer.id])
    out.seller_company_id = offer.company_id
    out.seller_legal_name = offer.company.legal_name if offer.company is not None else None
    if company_id is not None:
        company = company_or_404(db, account, company_id)
        out.is_own = offer.company_id is not None and offer.company_id == company.id
        out.my_inquiries = [
            OfferRequestOut.model_validate(i)
            for i in offer_request_service.list_company_inquiries_for_offer(
                db, company.id, offer_id
            )
        ]
    return out
