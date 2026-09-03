"""
/admin/moderation — seller-offer moderation queue (internal dashboard).

Analyst or admin only. Approve makes an offer public; reject returns a note to the
seller. Every decision is audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.marketplace import compliance as offer_compliance_service
from app.domains.marketplace import service as offer_service
from app.domains.marketplace.models import SellerOffer
from app.domains.marketplace.schemas import ModerationDecision, ModerationOfferOut, SellerOfferOut
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin/moderation", tags=["moderation"])


@router.get(
    "/offers",
    response_model=list[ModerationOfferOut],
    summary="List offers awaiting moderation",
)
def moderation_queue(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("moderation", "read")),
) -> list[ModerationOfferOut]:
    """GET /admin/moderation/offers — pending offers, oldest first.

    Each card carries its chemical-compliance block (FR-C5), evaluated now: the
    moderator is about to make the substance public, so a stale verdict is worse
    than none.
    """
    return [
        ModerationOfferOut.model_validate(offer).model_copy(
            update={"compliance": offer_compliance_service.verdict_out(db, offer)}
        )
        for offer in offer_service.list_pending(db)
    ]


def _get_pending(db: Session, offer_id: int) -> SellerOffer:
    offer: SellerOffer | None = db.query(SellerOffer).filter(SellerOffer.id == offer_id).first()
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


def _conflict(exc: offer_service.AlreadyModerated) -> HTTPException:
    """409 for a decision that lost the race — naming the status that won.

    "409" alone would leave a moderator wondering whether their click worked;
    the body says what the offer actually is now, so the UI can say
    "already rejected by someone else" and refresh the queue.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "already_moderated", "status": exc.current_status},
    )


@router.post(
    "/offers/{offer_id}/approve",
    response_model=SellerOfferOut,
    summary="Approve a seller offer (make it public)",
)
def approve_offer(
    offer_id: int,
    body: ModerationDecision,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("moderation", "write")),
) -> SellerOfferOut:
    """POST /admin/moderation/offers/{id}/approve.

    409 when chemical compliance blocks publication (FR-C4) — the body names
    what is missing so the moderator can tell the seller, or register the
    licence, instead of guessing why the button refused.

    409 as well when the offer already left the queue: two moderators acting on
    the same item (or one client retrying) must not each land half a decision.
    """
    offer = _get_pending(db, offer_id)
    try:
        offer_service.moderate_offer(db, offer, user.id, approve=True, note=body.note)
    except offer_compliance_service.CompliancePublishBlocked as exc:
        db.commit()  # keep the freshly stamped verdict; the approval itself is refused
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "compliance_blocked",
                "level": str(exc.verdict.level),
                "missing": exc.verdict.as_json(),
            },
        ) from exc
    except offer_service.AlreadyModerated as exc:
        raise _conflict(exc) from exc
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
    user: StaffUser = Depends(require_page("moderation", "write")),
) -> SellerOfferOut:
    """POST /admin/moderation/offers/{id}/reject.

    409 when the offer already left the queue — same exactly-once guard as approve.
    """
    offer = _get_pending(db, offer_id)
    try:
        offer_service.moderate_offer(db, offer, user.id, approve=False, note=body.note)
    except offer_service.AlreadyModerated as exc:
        raise _conflict(exc) from exc
    db.commit()
    return offer  # type: ignore[return-value]
