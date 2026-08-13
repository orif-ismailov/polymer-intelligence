"""Portal sample-request endpoints (P6 W3 — T3.2, FR-L3). Under /api/v1/portal.

A buyer asks for material to hold; the seller ships it; the buyer confirms it
arrived. Both sides use the same transition route — which party may make which
move is `sample_service._ACTOR_RULES`, not five hand-written verb routes each
with its own chance to forget the check.

Everything is company-scoped through membership: a request the caller's company
is not a party to is a 404, the same answer a non-member gets anywhere in the
portal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, require_business_role
from app.core.db import get_db
from app.domains.marketplace import service as offer_service
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.enums import SampleRequestStatus
from app.models.lab import SampleRequest
from app.schemas.lab import SampleRequestIn, SampleRequestOut, SampleTransitionIn
from app.services import company_service, sample_service

router = APIRouter(prefix="/portal", tags=["portal-samples"])


def _out(db: Session, sample: SampleRequest, *, company_id: int) -> SampleRequestOut:
    role = sample_service.acting_role(sample, company_id)
    other_id = (
        sample.buyer_company_id if role == "seller" else sample.seller_company_id
    )
    other = db.get(Company, other_id)
    offer = sample.offer
    return SampleRequestOut(
        id=sample.id,
        offer_id=sample.offer_id,
        offer_title=(offer.product_text or offer.grade_text) if offer else None,
        status=str(sample.status),
        buyer_company_id=sample.buyer_company_id,
        seller_company_id=sample.seller_company_id,
        counterparty_name=(
            (other.short_name or other.legal_name or other.tax_id) if other else None
        ),
        my_role=role,
        available_transitions=[
            str(s) for s in sample_service.available_transitions(sample.status, role)
        ],
        qty=sample.qty,
        delivery_address=sample.delivery_address,
        courier=sample.courier,
        tracking_ref=sample.tracking_ref,
        decline_reason=sample.decline_reason,
        accepted_at=sample.accepted_at,
        sent_at=sample.sent_at,
        received_at=sample.received_at,
        created_at=sample.created_at,
    )


@router.get("/companies/{company_id}/samples", response_model=list[SampleRequestOut])
def list_samples(
    company_id: int,
    side: str = Query(default="incoming", pattern="^(incoming|sent)$"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[SampleRequestOut]:
    """`incoming` — requests to answer; `sent` — requests we made."""
    company = company_or_404(db, account, company_id)
    return [
        _out(db, sample, company_id=company.id)
        for sample in sample_service.list_for_company(db, company.id, side=side)
    ]


@router.post(
    "/market/offers/{offer_id}/samples",
    response_model=SampleRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_sample(
    offer_id: int,
    body: SampleRequestIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleRequestOut:
    """Ask the seller for a sample of a public offer."""
    company = company_or_404(db, account, body.company_id)
    require_business_role(company, company_service.BUYER_CAPABLE_ROLES)
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    try:
        sample = sample_service.request(
            db,
            offer=offer,
            buyer_company=company,
            account=account,
            delivery_address=body.delivery_address,
            qty=body.qty,
        )
    except sample_service.SamplesNotAvailable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "samples_not_available"},
        ) from exc
    except sample_service.OwnOfferSample as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "own_offer"},
        ) from exc
    except sample_service.SampleRequestExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "already_requested"}
        ) from exc

    db.commit()
    db.refresh(sample)
    return _out(db, sample, company_id=company.id)


@router.post("/samples/{sample_id}/transition", response_model=SampleRequestOut)
def transition_sample(
    sample_id: int,
    body: SampleTransitionIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleRequestOut:
    """Accept, decline, ship, receive or reject — whichever your side may do.

    Refusals are separately coded so the portal can say what is wrong:
    `invalid_transition`, `not_your_move`, `reason_required`,
    `shipment_details_required`.
    """
    company = company_or_404(db, account, body.company_id)
    sample = db.get(SampleRequest, sample_id)
    if sample is None or sample.party_role(company.id) is None:
        # 404 for a request the caller's company is not part of: the same answer
        # a non-member gets, so probing an id reveals nothing.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if body.to_status not in {s.value for s in SampleRequestStatus}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
        )

    try:
        sample_service.transition(
            db,
            sample,
            SampleRequestStatus(body.to_status),
            acting_company_id=company.id,
            reason=body.reason,
            qty=body.qty,
            courier=body.courier,
            tracking_ref=body.tracking_ref,
        )
    except sample_service.ActorNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "not_your_move"}
        ) from exc
    except sample_service.InvalidSampleTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "invalid_transition"}
        ) from exc
    except sample_service.ReasonRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "reason_required"},
        ) from exc
    except sample_service.ShipmentDetailsRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "shipment_details_required"},
        ) from exc

    db.commit()
    db.refresh(sample)
    return _out(db, sample, company_id=company.id)
