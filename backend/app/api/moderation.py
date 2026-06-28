"""
/admin/moderation — seller-offer moderation queue (internal dashboard).

Analyst or admin only. Approve makes an offer public; reject returns a note to the
seller. Every decision is audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.models.marketplace import SellerOffer
from app.models.staff import StaffUser
from app.schemas.marketplace import ModerationDecision, ModerationOfferOut, SellerOfferOut
from app.services import offer_service

router = APIRouter(prefix="/admin/moderation", tags=["moderation"])


@router.get(
    "/offers",
    response_model=list[ModerationOfferOut],
    summary="List offers awaiting moderation",
)
def moderation_queue(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[ModerationOfferOut]:
    """GET /admin/moderation/offers — pending offers, oldest first."""
    return offer_service.list_pending(db)  # type: ignore[return-value]


def _get_pending(db: Session, offer_id: int) -> SellerOffer:
    offer: SellerOffer | None = db.query(SellerOffer).filter(SellerOffer.id == offer_id).first()
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.post(
    "/offers/{offer_id}/approve",
    response_model=SellerOfferOut,
    summary="Approve a seller offer (make it public)",
)
def approve_offer(
    offer_id: int,
    body: ModerationDecision,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_analyst_or_admin),
) -> SellerOfferOut:
    """POST /admin/moderation/offers/{id}/approve."""
    offer = _get_pending(db, offer_id)
    offer_service.moderate_offer(db, offer, user.id, approve=True, note=body.note)
    db.commit()
    return offer  # type: ignore[return-value]


@router.post(
    "/offers/{offer_id}/reject",
    response_model=SellerOfferOut,
    summary="Reject a seller offer (with a note)",
)
def reject_offer(
    offer_id: int,
    body: ModerationDecision,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_analyst_or_admin),
) -> SellerOfferOut:
    """POST /admin/moderation/offers/{id}/reject."""
    offer = _get_pending(db, offer_id)
    offer_service.moderate_offer(db, offer, user.id, approve=False, note=body.note)
    db.commit()
    return offer  # type: ignore[return-value]
