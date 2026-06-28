"""
/webapp/market — public seller-offer catalog (Telegram Web App).

Only `approved` offers are returned (per-offer moderation gate). Authenticated via
initData like the rest of the webapp surface. Buyer requests are NEVER exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.marketplace import SellerOfferFile
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


@router.get(
    "/offers/{offer_id}/images/{file_id}",
    summary="Stream an approved offer's file (public — for <img> tags)",
)
def get_offer_image(
    offer_id: int,
    file_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """GET an offer file's bytes. PUBLIC (no initData) so <img src> works; only files
    belonging to an APPROVED offer are served. Reads from S3/MinIO and proxies the bytes.
    """
    # Approved-only gate (catalog visibility); reuses the service's approved filter.
    if offer_service.get_catalog_offer(db, offer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    f = (
        db.query(SellerOfferFile)
        .filter(SellerOfferFile.id == file_id, SellerOfferFile.offer_id == offer_id)
        .first()
    )
    if f is None or f.storage_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=f.storage_path)  # type: ignore[attr-defined]
    body: bytes = obj["Body"].read()
    return Response(content=body, media_type=f.mime_type or "application/octet-stream")
