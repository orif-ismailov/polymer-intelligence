"""
/webapp/seller — seller offer create + own-offers list (Telegram Web App).

Open self-serve: the Seller is upserted from the verified initData identity
(get_current_client); offers go straight to moderation. No identity in the body.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.enums import OfferFileKind, SellerOfferStatus
from app.models.marketplace import Seller, SellerOffer, SellerOfferFile
from app.models.requests import Client
from app.schemas.marketplace import (
    OfferFileRef,
    SellerOfferCreate,
    SellerOfferOut,
    SellerOfferUpdate,
)
from app.services import offer_service, storage_service
from app.services.storage_service import MAX_OFFER_FILES

router = APIRouter(prefix="/webapp/seller", tags=["webapp-seller"])


def _own_offer(db: Session, offer_id: int, client: Client) -> SellerOffer:
    """Load the caller's own offer or 404 (owner-scoped: a foreign/absent id looks missing).

    Resolves the Seller from the verified Telegram identity, then the offer scoped to that
    seller — so only the owner can read/edit a listing (IDOR-safe; T-03-07 pattern).
    """
    seller = db.query(Seller).filter(Seller.telegram_user_id == client.telegram_user_id).first()
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    offer = offer_service.get_own_offer(db, offer_id, seller.id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.post(
    "/offers",
    response_model=SellerOfferOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a seller offer (submitted to moderation)",
)
def create_offer(
    body: SellerOfferCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> SellerOfferOut:
    """POST /webapp/seller/offers — create an offer in `pending_moderation`.

    The seller is resolved/created from the verified Telegram identity.
    """
    if client.telegram_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        seller = offer_service.get_or_create_seller(
            db, telegram_user_id=client.telegram_user_id, data=body
        )
        offer = offer_service.create_offer(db, seller, body)
        db.commit()
        return offer  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/offers",
    response_model=list[SellerOfferOut],
    summary="List the authenticated seller's own offers",
)
def list_my_offers(
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> list[SellerOfferOut]:
    """GET /webapp/seller/offers — the caller's own offers (any status), newest first."""
    seller: Seller | None = (
        db.query(Seller).filter(Seller.telegram_user_id == client.telegram_user_id).first()
    )
    if seller is None:
        return []
    return offer_service.list_seller_offers(db, seller.id)  # type: ignore[return-value]


@router.get(
    "/offers/{offer_id}",
    response_model=SellerOfferOut,
    summary="Get one of the caller's own offers (any status)",
)
def get_my_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> SellerOfferOut:
    """GET /webapp/seller/offers/{id} — the caller's own offer (for the edit screen), or 404."""
    return _own_offer(db, offer_id, client)  # type: ignore[return-value]


@router.patch(
    "/offers/{offer_id}",
    response_model=SellerOfferOut,
    summary="Edit one's own offer (re-enters moderation when it was already public)",
)
def update_my_offer(
    offer_id: int,
    body: SellerOfferUpdate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> SellerOfferOut:
    """PATCH /webapp/seller/offers/{id} — revise one's own offer (full-replacement body).

    Only the owner can edit (foreign/absent id → 404). Editing an offer that is already
    public (approved) — or was rejected — sends it back to moderation and re-posts it to
    the team group for re-approval; draft/pending offers are updated in place.
    """
    offer = _own_offer(db, offer_id, client)
    try:
        offer, requeued = offer_service.update_offer(db, offer, body)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if requeued:
        offer_service.enqueue_offer_group_notify(offer.id, edited=True)
    return offer  # type: ignore[return-value]


@router.post(
    "/offers/{offer_id}/submit",
    summary="Finalize an offer (uploads done) → notify the team group",
)
def submit_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> dict[str, bool]:
    """POST /webapp/seller/offers/{id}/submit — called by the webapp once the offer's
    files have finished uploading. Posts the offer (with its image + seller details +
    Confirm button) to the team Telegram group so an admin can approve it from chat.

    Best-effort: enqueues only while the offer is still awaiting moderation, so a
    duplicate call (or one after a dashboard decision) does not re-notify.
    """
    offer = _own_offer(db, offer_id, client)
    if offer.status == SellerOfferStatus.pending_moderation:
        offer_service.enqueue_offer_group_notify(offer.id)
    return {"ok": True}


@router.post(
    "/offers/{offer_id}/files",
    response_model=OfferFileRef,
    status_code=status.HTTP_201_CREATED,
    summary="Attach an image / TDS / certificate to one's own offer",
)
async def upload_offer_file(
    offer_id: int,
    file: UploadFile = File(...),
    kind: str = Query(default="image"),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> OfferFileRef:
    """POST /webapp/seller/offers/{id}/files — upload a file to the caller's own offer."""
    _own_offer(db, offer_id, client)  # owner-scoped guard (404 for foreign/absent)

    existing = db.query(SellerOfferFile).filter(SellerOfferFile.offer_id == offer_id).count()
    if existing >= MAX_OFFER_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="too_many_files")

    try:
        file_kind = OfferFileKind(kind)
    except ValueError:
        file_kind = OfferFileKind.other

    content = await file.read()
    try:
        f = storage_service.upload_offer_file(
            db, offer_id, content, file.filename or "upload", file_kind
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return OfferFileRef(id=f.id, kind=f.kind, file_name=f.file_name)
