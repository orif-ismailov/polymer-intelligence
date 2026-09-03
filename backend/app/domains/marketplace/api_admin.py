"""
/admin/offer-requests — review queue for buyer "Request an offer" inquiries.

Analyst or admin only. Approve forwards the inquiry to the seller by bot DM (buyer
contact withheld); reject closes it with an optional note. Staff see both parties'
contacts here so they can broker the deal. Every decision is audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.marketplace import requests as offer_request_service
from app.domains.marketplace.models import OfferRequest
from app.domains.marketplace.schemas import AdminOfferRequestOut, ModerationDecision
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin/offer-requests", tags=["offer-requests"])


@router.get(
    "",
    response_model=list[AdminOfferRequestOut],
    summary="List pending buyer inquiries awaiting review",
)
def review_queue(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("offerRequests", "read")),
) -> list[AdminOfferRequestOut]:
    """GET /admin/offer-requests — pending inquiries, oldest first."""
    return [offer_request_service.to_admin_out(r) for r in offer_request_service.list_pending(db)]


def _get_pending(db: Session, offer_request_id: int) -> OfferRequest:
    req = offer_request_service.get_offer_request(db, offer_request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inquiry not found")
    return req


def _conflict(exc: offer_request_service.AlreadyModerated) -> HTTPException:
    """409 for a decision that lost the race — naming the status that won."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "already_moderated", "status": exc.current_status},
    )


@router.post(
    "/{offer_request_id}/approve",
    response_model=AdminOfferRequestOut,
    summary="Approve an inquiry → forward to the seller",
)
def approve_offer_request(
    offer_request_id: int,
    body: ModerationDecision,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("offerRequests", "write")),
) -> AdminOfferRequestOut:
    """POST /admin/offer-requests/{id}/approve.

    409 when the inquiry already left the queue — two reviewers must not each
    land half a decision (see `offer_request_service._claim_pending`).
    """
    req = _get_pending(db, offer_request_id)
    try:
        offer_request_service.moderate_offer_request(db, req, user.id, approve=True, note=body.note)
    except offer_request_service.AlreadyModerated as exc:
        raise _conflict(exc) from exc
    db.commit()
    offer_request_service.enqueue_offer_request_to_seller(req.id)
    return offer_request_service.to_admin_out(req)


@router.post(
    "/{offer_request_id}/reject",
    response_model=AdminOfferRequestOut,
    summary="Reject an inquiry (with an optional note)",
)
def reject_offer_request(
    offer_request_id: int,
    body: ModerationDecision,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("offerRequests", "write")),
) -> AdminOfferRequestOut:
    """POST /admin/offer-requests/{id}/reject.

    409 when the inquiry already left the queue — same exactly-once guard as approve.
    """
    req = _get_pending(db, offer_request_id)
    try:
        offer_request_service.moderate_offer_request(
            db, req, user.id, approve=False, note=body.note
        )
    except offer_request_service.AlreadyModerated as exc:
        raise _conflict(exc) from exc
    db.commit()
    return offer_request_service.to_admin_out(req)
