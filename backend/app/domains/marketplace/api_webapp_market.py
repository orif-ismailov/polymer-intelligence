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
from app.domains.companies.models import Company
from app.domains.marketplace import requests as offer_request_service
from app.domains.marketplace import service as offer_service
from app.domains.marketplace.models import SellerOfferFile
from app.domains.marketplace.schemas import (
    CatalogOfferOut,
    CategoryCount,
    OfferRequestCreate,
    OfferRequestOut,
    OfferRequestUpdate,
    PublicFeaturedOffer,
)
from app.domains.requests.models import Client

router = APIRouter(prefix="/webapp/market", tags=["webapp-market"])


@router.get(
    "/featured",
    response_model=list[PublicFeaturedOffer],
    summary="Public featured offers for the marketing landing (NO auth, NO seller contact)",
)
def list_featured(
    limit: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[PublicFeaturedOffer]:
    """GET /webapp/market/featured — a few approved offers for the anonymous landing.

    PUBLIC (no get_current_client): the IMEX AI landing is served to unauthenticated
    browser visitors. Reuses the approved-only catalog query but maps to
    PublicFeaturedOffer, which OMITS the seller contact block — supplier contacts stay
    behind Telegram auth in the /market screen. Images render via the already-public
    /webapp/market/offers/{id}/images/{file_id} route.
    """
    offers = offer_service.list_catalog(db, limit=limit, offset=0)
    return [PublicFeaturedOffer.model_validate(o) for o in offers]


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
    client: Client = Depends(get_current_client),
) -> list[CatalogOfferOut]:
    """GET /webapp/market/offers — approved offers, optional product/free-text filter.

    Excludes the caller's own listings: a seller browsing the marketplace sees only other
    sellers' offers (they manage their own under "My offers" and cannot inquire on them).
    """
    exclude_seller_id = offer_service.seller_id_for(db, client.telegram_user_id)
    offers = offer_service.list_catalog(
        db,
        product_id=product_id,
        q=q,
        exclude_seller_id=exclude_seller_id,
        limit=limit,
        offset=offset,
    )
    return offers  # type: ignore[return-value]


@router.get(
    "/categories",
    response_model=list[CategoryCount],
    summary="Catalog category chips with approved-offer counts",
)
def list_categories(
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> list[CategoryCount]:
    """GET /webapp/market/categories — per-product approved-offer counts (own excluded)."""
    exclude_seller_id = offer_service.seller_id_for(db, client.telegram_user_id)
    return offer_service.category_counts(db, exclude_seller_id=exclude_seller_id)


@router.get(
    "/offers/{offer_id}",
    response_model=CatalogOfferOut,
    summary="Get a public catalog offer",
)
def get_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> CatalogOfferOut:
    """GET /webapp/market/offers/{id} — a single approved offer, or 404.

    Sets ``is_own`` when the caller owns the offer so the client can hide the
    "Request an offer" action (a seller can't inquire on its own listing).
    """
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    out = CatalogOfferOut.model_validate(offer)
    my_seller_id = offer_service.seller_id_for(db, client.telegram_user_id)
    out.is_own = my_seller_id is not None and offer.seller_id == my_seller_id
    return out


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


@router.get(
    "/companies/{company_id}/logo",
    summary="Stream a company logo (public — for <img> tags)",
)
def get_company_logo(company_id: int, db: Session = Depends(get_db)) -> Response:
    """GET a company logo's bytes.

    PUBLIC and byte-proxied for the same reason as `get_offer_image`: a presigned
    S3 URL is signed against the INTERNAL endpoint (`http://minio:9000`), which no
    browser can resolve, so every `<img src>` built from one is a broken image.
    Proxying through the API keeps logos on the same origin as the rest of the app.

    A logo is brand material shown on the public catalog, so no auth gate — but the
    key is read from the row, never from the caller, so this cannot be walked to
    other objects in the bucket.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None or not company.logo_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=company.logo_storage_path)  # type: ignore[attr-defined]
    body = obj["Body"].read()
    media_type = "image/png" if company.logo_storage_path.endswith(".png") else "image/jpeg"
    return Response(content=body, media_type=media_type)


@router.get(
    "/companies/{company_id}/cover",
    summary="Stream a company cover image (public — for <img> tags)",
)
def get_company_cover(company_id: int, db: Session = Depends(get_db)) -> Response:
    """GET a company cover's bytes — same proxy contract as the logo above."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None or not company.cover_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=company.cover_storage_path)  # type: ignore[attr-defined]
    body = obj["Body"].read()
    media_type = "image/png" if company.cover_storage_path.endswith(".png") else "image/jpeg"
    return Response(content=body, media_type=media_type)


@router.get(
    "/companies/{company_id}/media/{media_id}",
    summary="Stream a company media image (public — for <img> tags)",
)
def get_company_media(
    company_id: int, media_id: int, db: Session = Depends(get_db)
) -> Response:
    """GET one of a company's images.

    The company id is in the path AND checked against the row: without that, a
    bare media id would be a handle to every image in the bucket regardless of
    who owns it. The storage key still comes from the row, never the caller.
    """
    from app.models.media import CompanyMedia  # noqa: PLC0415

    media = (
        db.query(CompanyMedia)
        .filter(CompanyMedia.id == media_id, CompanyMedia.company_id == company_id)
        .first()
    )
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=media.storage_path)  # type: ignore[attr-defined]
    return Response(content=obj["Body"].read(), media_type=media.mime_type)


@router.post(
    "/offers/{offer_id}/request",
    response_model=OfferRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request an offer (buyer inquiry → admin review → seller)",
)
def request_offer(
    offer_id: int,
    body: OfferRequestCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> OfferRequestOut:
    """POST /webapp/market/offers/{id}/request — create a `pending` inquiry.

    The inquiry is reviewed by staff (dashboard queue + team group) and, once
    approved, forwarded to the seller by bot DM. Identity is the verified client;
    there is no buyer-contact field in the body.

    Raises:
        HTTP 404/422: offer missing or not public → ValueError → 422.
    """
    try:
        req = offer_request_service.create_offer_request(db, client, offer_id, body)
        db.commit()
        offer_request_service.enqueue_offer_request_to_group(req.id)
        return req  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/my-requests",
    response_model=list[OfferRequestOut],
    summary="List the authenticated buyer's own offer inquiries",
)
def list_my_offer_requests(
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> list[OfferRequestOut]:
    """GET /webapp/market/my-requests — the caller's inquiries with status, newest first."""
    return offer_request_service.list_for_client(db, client.id)  # type: ignore[return-value]


def _own_offer_request(db: Session, offer_request_id: int, client: Client) -> object:
    """Load the caller's own inquiry or 404 (IDOR-safe: a foreign id looks missing)."""
    req = offer_request_service.get_offer_request(db, offer_request_id)
    if req is None or req.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return req


@router.get(
    "/my-requests/{offer_request_id}",
    response_model=OfferRequestOut,
    summary="Get one of the buyer's own inquiries (detail)",
)
def get_my_offer_request(
    offer_request_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> OfferRequestOut:
    """GET /webapp/market/my-requests/{id} — the caller's own inquiry, or 404."""
    return _own_offer_request(db, offer_request_id, client)  # type: ignore[return-value]


@router.patch(
    "/my-requests/{offer_request_id}",
    response_model=OfferRequestOut,
    summary="Edit the buyer's own inquiry (re-review + notify seller of changes)",
)
def update_my_offer_request(
    offer_request_id: int,
    body: OfferRequestUpdate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> OfferRequestOut:
    """PATCH /webapp/market/my-requests/{id} — revise one's own inquiry.

    Saves the changes, records the edit, and (when anything actually changed) re-posts
    the inquiry to the team group for review — marked as updated, with a diff. Editing an
    already-approved inquiry sends it back to `pending`; on re-approval the seller is
    DM'd that the buyer updated their request (see the notify tasks). A rejected inquiry
    can't be edited (422).
    """
    req = _own_offer_request(db, offer_request_id, client)
    try:
        req, changes = offer_request_service.update_offer_request(db, req, body)  # type: ignore[arg-type]
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if changes:
        offer_request_service.enqueue_offer_request_to_group(req.id)
    return req  # type: ignore[return-value]
