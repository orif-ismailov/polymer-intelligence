"""
/webapp/seller — seller offer create + own-offers list (Telegram Web App).

Open self-serve: the Seller is upserted from the verified initData identity
(get_current_client); offers go straight to moderation. No identity in the body.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.marketplace import Seller
from app.models.requests import Client
from app.schemas.marketplace import SellerOfferCreate, SellerOfferOut
from app.services import offer_service

router = APIRouter(prefix="/webapp/seller", tags=["webapp-seller"])


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
