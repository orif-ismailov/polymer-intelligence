"""Staff lab API (P6 W2 — T2.4). Under /api/v1/admin.

The operator's work list. The analysis is a manual process, so this is where the
whole lifecycle actually happens: pick up a request, agree it with a partner
laboratory, wait for the sample, wait for the result, upload the passport.

Authz mirrors the rest of the admin surface rather than escrow's tighter rule:
an analyst RUNS this queue (it is their job), while the partner DIRECTORY —
which decides who we send other people's material to — is admin-only.

`done` is not in the transition endpoint. It needs the passport, so it has its
own multipart route; the state machine and the schema both refuse a `done` with
nothing behind it.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_analyst_or_admin
from app.core.db import get_db
from app.models.companies import Company
from app.models.enums import LabOrderStatus
from app.models.lab import LabOrder, LabPartner
from app.models.staff import StaffUser
from app.schemas.lab import LabPartnerIn, LabPartnerOut
from app.services import deal_service, lab_service

router = APIRouter(prefix="/admin", tags=["admin-lab"])


# ── schemas ───────────────────────────────────────────────────────────────────


class LabOrderAdminOut(BaseModel):
    """A lab order as the operator sees it — with who asked and what for."""

    id: int
    number: str
    status: str
    company_id: int
    company_name: str | None = None
    offer_id: int | None = None
    offer_title: str | None = None
    deal_id: int | None = None
    substance_id: int | None = None
    substance_name: str | None = None
    sample_volume: str | None = None
    comment: str | None = None
    lab_partner_id: int | None = None
    lab_partner_name: str | None = None
    operator_note: str | None = None
    rejected_reason: str | None = None
    result_offer_file_id: int | None = None
    result_deal_document_id: int | None = None
    handled_by: int | None = None
    #: Statuses this order may move to right now — the dashboard builds its
    #: buttons from this rather than re-deriving the machine in TypeScript.
    available_transitions: list[str] = Field(default_factory=list)
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LabCountersOut(BaseModel):
    """The whole board, not the filtered page."""

    submitted: int
    in_progress: int
    done: int
    rejected: int


class LabOrderListOut(BaseModel):
    items: list[LabOrderAdminOut]
    counters: LabCountersOut


class TransitionIn(BaseModel):
    to_status: str
    #: Mandatory for `rejected` (enforced by the service), otherwise stored as the
    #: operator's running note on the order.
    note: str | None = Field(default=None, max_length=1000)


class AssignPartnerIn(BaseModel):
    lab_partner_id: int


# ── helpers ───────────────────────────────────────────────────────────────────


def _company_name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:  # pragma: no cover — FK guarantees it
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, order: LabOrder) -> LabOrderAdminOut:
    offer = order.offer
    return LabOrderAdminOut(
        id=order.id,
        number=order.number,
        status=str(order.status),
        company_id=order.company_id,
        company_name=_company_name(db, order.company_id),
        offer_id=order.offer_id,
        offer_title=(offer.product_text or offer.grade_text) if offer is not None else None,
        deal_id=order.deal_id,
        substance_id=order.substance_id,
        substance_name=order.substance.name_ru if order.substance is not None else None,
        sample_volume=order.sample_volume,
        comment=order.comment,
        lab_partner_id=order.lab_partner_id,
        lab_partner_name=order.partner.name if order.partner is not None else None,
        operator_note=order.operator_note,
        rejected_reason=order.rejected_reason,
        result_offer_file_id=order.result_offer_file_id,
        result_deal_document_id=order.result_deal_document_id,
        handled_by=order.handled_by,
        available_transitions=[
            str(s) for s in lab_service.available_transitions(order.status)
        ],
        completed_at=order.completed_at,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _order_or_404(db: Session, order_id: int) -> LabOrder:
    order = lab_service.get(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab order not found")
    return order


# ── the queue ─────────────────────────────────────────────────────────────────


@router.get("/lab-orders", response_model=LabOrderListOut)
def list_lab_orders(
    order_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> LabOrderListOut:
    parsed: LabOrderStatus | None = None
    if order_status:
        if order_status not in {s.value for s in LabOrderStatus}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
            )
        parsed = LabOrderStatus(order_status)

    rows = lab_service.list_queue(db, status=parsed, limit=limit, offset=offset)
    by_status = dict(
        db.query(LabOrder.status, func.count(LabOrder.id)).group_by(LabOrder.status).all()
    )
    return LabOrderListOut(
        items=[_out(db, order) for order in rows],
        counters=LabCountersOut(
            submitted=by_status.get(LabOrderStatus.submitted, 0),
            in_progress=(
                by_status.get(LabOrderStatus.accepted, 0)
                + by_status.get(LabOrderStatus.sample_awaited, 0)
                + by_status.get(LabOrderStatus.in_analysis, 0)
            ),
            done=by_status.get(LabOrderStatus.done, 0),
            rejected=by_status.get(LabOrderStatus.rejected, 0),
        ),
    )


@router.get("/lab-orders/{order_id}", response_model=LabOrderAdminOut)
def get_lab_order(
    order_id: int,
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> LabOrderAdminOut:
    return _out(db, _order_or_404(db, order_id))


@router.post("/lab-orders/{order_id}/transition", response_model=LabOrderAdminOut)
def transition_lab_order(
    order_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> LabOrderAdminOut:
    """Move an order along.

    Each refusal has its own code, because "409" tells an operator nothing about
    what to do next: `invalid_transition` (the machine says no),
    `reason_required` (a rejection has to be explainable), `result_required`
    (`done` needs the passport — use the result route).
    """
    order = _order_or_404(db, order_id)
    if body.to_status not in {s.value for s in LabOrderStatus}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
        )

    try:
        lab_service.transition(
            db, order, LabOrderStatus(body.to_status), staff_user=staff, note=body.note
        )
    except lab_service.LabResultRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="result_required"
        ) from exc
    except lab_service.ReasonRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reason_required"
        ) from exc
    except lab_service.InvalidLabTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid_transition"
        ) from exc

    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.post("/lab-orders/{order_id}/result", response_model=LabOrderAdminOut)
async def upload_lab_result(
    order_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> LabOrderAdminOut:
    """Finish an order by uploading the passport (PDF).

    The document lands on the offer (and flips its `lab_verified`) or in the
    deal's Trade Room, depending on what the order was about.
    """
    order = _order_or_404(db, order_id)
    content = await file.read()

    try:
        lab_service.complete_with_result(
            db,
            order,
            staff_user=staff,
            content=content,
            filename=file.filename or "passport.pdf",
        )
    except lab_service.InvalidResultFile as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except lab_service.InvalidLabTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid_transition"
        ) from exc
    except deal_service.NotDealParticipant as exc:
        # The person who ordered the analysis has since left the party company,
        # so there is nobody to attribute the document to. Rare, but it would
        # otherwise surface as a 500 while an operator holds a PDF.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="orderer_left_the_deal"
        ) from exc

    if note:
        order.operator_note = note
    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.post("/lab-orders/{order_id}/partner", response_model=LabOrderAdminOut)
def assign_lab_partner(
    order_id: int,
    body: AssignPartnerIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_analyst_or_admin),
) -> LabOrderAdminOut:
    """Record which laboratory is doing the work. Not a status change."""
    order = _order_or_404(db, order_id)
    partner = lab_service.get_partner(db, body.lab_partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    lab_service.assign_partner(db, order, partner, staff_user=staff)
    db.commit()
    db.refresh(order)
    return _out(db, order)


# ── the partner directory (admin only) ────────────────────────────────────────


@router.get("/lab-partners", response_model=list[LabPartnerOut])
def list_lab_partners(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> list[LabPartner]:
    """Readable by analysts — they pick a partner when assigning an order."""
    return lab_service.list_partners(db, active_only=active_only)


@router.post(
    "/lab-partners", response_model=LabPartnerOut, status_code=status.HTTP_201_CREATED
)
def create_lab_partner(
    body: LabPartnerIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> LabPartner:
    partner = lab_service.create_partner(
        db,
        name=body.name,
        contacts=dict(body.contacts),
        company_id=body.company_id,
        note=body.note,
        staff_user_id=staff.id,
    )
    db.commit()
    db.refresh(partner)
    return partner


@router.patch("/lab-partners/{partner_id}", response_model=LabPartnerOut)
def update_lab_partner(
    partner_id: int,
    body: LabPartnerIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> LabPartner:
    partner = _partner_or_404(db, partner_id)
    lab_service.update_partner(
        db,
        partner,
        staff_user_id=staff.id,
        name=body.name,
        contacts=dict(body.contacts),
        company_id=body.company_id,
        note=body.note,
    )
    db.commit()
    db.refresh(partner)
    return partner


@router.post("/lab-partners/{partner_id}/deactivate", response_model=LabPartnerOut)
def deactivate_lab_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> LabPartner:
    """Retire a laboratory. There is no DELETE: a finished order points at the
    lab that ran it, and that answer has to survive the partnership."""
    partner = _partner_or_404(db, partner_id)
    lab_service.set_partner_active(db, partner, False, staff_user_id=staff.id)
    db.commit()
    db.refresh(partner)
    return partner


@router.post("/lab-partners/{partner_id}/activate", response_model=LabPartnerOut)
def activate_lab_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> LabPartner:
    partner = _partner_or_404(db, partner_id)
    lab_service.set_partner_active(db, partner, True, staff_user_id=staff.id)
    db.commit()
    db.refresh(partner)
    return partner


def _partner_or_404(db: Session, partner_id: int) -> LabPartner:
    partner = lab_service.get_partner(db, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return partner
