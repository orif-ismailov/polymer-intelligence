"""
/webapp/market — public seller-offer catalog (Telegram Web App).

Only `approved` offers are returned (per-offer moderation gate). Authenticated via
initData like the rest of the webapp surface. Buyer requests are NEVER exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.requests import Client
from app.schemas.marketplace import CatalogOfferOut, CategoryCount
from app.services import offer_service

router = APIRouter(prefix="/webapp/market", tags=["webapp-market"])


@router.get(
    "/offers",
    response_model=list[CatalogOfferOut],
    summary="List public catalog offers (approved)",
)
def list_offers(
    product_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[CatalogOfferOut]:
    """GET /webapp/market/offers — approved offers, optional product/free-text filter."""
    offers = offer_service.list_catalog(db, product_id=product_id, q=q, limit=limit, offset=offset)
    return offers  # type: ignore[return-value]


@router.get(
    "/categories",
    response_model=list[CategoryCount],
    summary="Catalog category chips with approved-offer counts",
)
def list_categories(
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[CategoryCount]:
    """GET /webapp/market/categories — per-product approved-offer counts."""
    return offer_service.category_counts(db)


@router.get(
    "/offers/{offer_id}",
    response_model=CatalogOfferOut,
    summary="Get a public catalog offer",
)
def get_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> CatalogOfferOut:
    """GET /webapp/market/offers/{id} — a single approved offer, or 404."""
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer  # type: ignore[return-value]
