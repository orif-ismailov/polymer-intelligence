"""Portal lab-order endpoints (P6 W2 — T2.3, FR-L2). Under /api/v1/portal.

A seller with no laboratory passport asks us to arrange one; a party to a deal
asks for the material in flight to be checked. Both raise the same `LabOrder`
and both are handled by a human afterwards — the response says as much, and the
portal shows the "we will call you to agree the laboratory, the price and how to
hand over the sample" copy next to it.

There is no status endpoint here on purpose: the customer watches, staff drive
(`/admin/lab-orders`). Nothing a customer could press would make a laboratory
work faster.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.deals.models import Deal
from app.domains.lab_orders import service as lab_service
from app.domains.lab_orders.models import LabOrder
from app.domains.lab_orders.schemas import LabOrderIn, LabOrderOut
from app.domains.marketplace.models import SellerOffer

router = APIRouter(prefix="/portal/companies", tags=["portal-lab"])


def _out(order: LabOrder) -> LabOrderOut:
    payload = LabOrderOut.model_validate(order)
    payload.lab_partner_name = order.partner.name if order.partner is not None else None
    return payload


def _order_or_404(db: Session, company_id: int, order_id: int) -> LabOrder:
    order = (
        db.query(LabOrder)
        .filter(LabOrder.id == order_id, LabOrder.company_id == company_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab order not found")
    return order


@router.get("/{company_id}/lab-orders", response_model=list[LabOrderOut])
def list_lab_orders(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[LabOrderOut]:
    company = company_or_404(db, account, company_id)
    return [_out(order) for order in lab_service.list_for_company(db, company.id)]


@router.post(
    "/{company_id}/lab-orders",
    response_model=LabOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_lab_order(
    company_id: int,
    body: LabOrderIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabOrderOut:
    """Raise a request for an analysis, about one of your offers or your deals."""
    company = company_or_404(db, account, company_id)

    offer = db.get(SellerOffer, body.offer_id) if body.offer_id is not None else None
    deal = db.get(Deal, body.deal_id) if body.deal_id is not None else None
    if (body.offer_id is not None and offer is None) or (
        body.deal_id is not None and deal is None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    try:
        order = lab_service.create_order(
            db,
            company=company,
            account=account,
            offer=offer,
            deal=deal,
            substance_id=body.substance_id,
            sample_volume=body.sample_volume,
            comment=body.comment,
        )
    except lab_service.LabOrderNotAllowed as exc:
        # 404, not 403: the same answer a non-member gets, so probing an offer id
        # tells an outsider nothing about whether it exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target not found"
        ) from exc
    except lab_service.LabOrderTargetMissing as exc:  # pragma: no cover — schema guards it
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_required"
        ) from exc

    db.commit()
    db.refresh(order)
    return _out(order)


@router.get("/{company_id}/lab-orders/{order_id}", response_model=LabOrderOut)
def get_lab_order(
    company_id: int,
    order_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabOrderOut:
    company = company_or_404(db, account, company_id)
    return _out(_order_or_404(db, company.id, order_id))
