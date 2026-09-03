"""Staff escrow API (R4 / P3 — T2.2). Under /api/v1/admin.

The operator's day, in two queues: who owes us money (`pending`), and who we owe
money to (`funded`, once delivery is confirmed). Plus a third list nobody else
would surface — signed deals with no agreed total, which cannot be invoiced and
would otherwise sit invisible at `contract_signed` forever.

Marking money is the most consequential button in the product, so the authz is
tighter than the rest of the admin surface:

  * an analyst may WATCH the queue but not move a payment (`require_admin` on
    the mutation, `require_analyst_or_admin` on the reads);
  * even an admin must send `confirmed: true` — the dashboard's "I confirm the
    funds actually moved in the bank" checkbox means nothing if the API accepts
    a mark without it;
  * the note is mandatory and is the operator's link to the bank record.

There is no edit or delete path. A payment row is evidence: it is marked
forward, never rewritten.
"""

from __future__ import annotations

import datetime
import decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.deals import escrow as escrow_service
from app.domains.deals import service as deal_service
from app.domains.deals.models import Deal
from app.domains.deals.payment_models import EscrowPayment
from app.models.enums import DealStatus, EscrowStatus
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin", tags=["admin-escrow"])


# ── schemas ───────────────────────────────────────────────────────────────────


class EscrowPaymentOut(BaseModel):
    id: int
    deal_id: int
    deal_number: str
    deal_status: str
    status: str
    mode: str
    amount: decimal.Decimal
    currency: str
    buyer_company_id: int
    buyer_name: str | None = None
    seller_company_id: int
    seller_name: str | None = None
    funded_at: datetime.datetime | None = None
    released_at: datetime.datetime | None = None
    refunded_at: datetime.datetime | None = None
    note: str | None = None
    provider_ref: str | None = None
    #: Statuses this payment may be marked to right now — the UI builds its
    #: buttons from this rather than re-deriving the machine in TypeScript.
    available_marks: list[str] = Field(default_factory=list)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("amount")
    def _amount(self, value: decimal.Decimal) -> str:
        return f"{value:.2f}"


class BlockedDealOut(BaseModel):
    """A signed deal that cannot be invoiced. Staff have to fix it by hand."""

    deal_id: int
    deal_number: str
    buyer_name: str | None = None
    seller_name: str | None = None
    reason: str
    created_at: datetime.datetime


class EscrowCountersOut(BaseModel):
    awaiting_funds: int
    awaiting_payout: int
    settled: int
    blocked: int
    #: Bank callbacks we understood and deliberately did not apply (R6 / P7.b).
    #: Surfaced in the counters so an operator sees there is something to
    #: reconcile without opening another tab.
    provider_holds: int = 0


class ProviderHoldOut(BaseModel):
    """A provider callback that was recorded, explained, and left to a human.

    `claimed_status` is what the bank says; `payment_status` is what we record.
    The row exists precisely because the two disagree — and it disappears from
    this list once an operator's manual mark makes them agree, which is why
    there is no resolve button.
    """

    event_id: int
    provider: str
    external_id: str
    reason: str
    detail: str
    claimed_status: str | None = None
    payment_id: int | None = None
    payment_status: str | None = None
    deal_id: int | None = None
    created_at: datetime.datetime


class ProviderHoldListOut(BaseModel):
    items: list[ProviderHoldOut]


class EscrowListOut(BaseModel):
    items: list[EscrowPaymentOut]
    blocked: list[BlockedDealOut] = Field(default_factory=list)
    counters: EscrowCountersOut


class MarkIn(BaseModel):
    to_status: str
    #: The bank reference / statement line. Without it the row is an
    #: unfalsifiable claim that money moved.
    note: str = Field(min_length=1, max_length=1000)
    #: Mirrors the dashboard's confirmation checkbox. Required server-side too,
    #: because a UI-only confirmation is no confirmation at all.
    confirmed: bool = False


# ── helpers ───────────────────────────────────────────────────────────────────


def _name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:  # pragma: no cover — FK guarantees it
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, payment: EscrowPayment, deal: Deal) -> EscrowPaymentOut:
    return EscrowPaymentOut(
        id=payment.id,
        deal_id=deal.id,
        deal_number=deal.number,
        deal_status=str(deal.status),
        status=str(payment.status),
        mode=payment.mode,
        amount=payment.amount,
        currency=payment.currency,
        buyer_company_id=deal.buyer_company_id,
        buyer_name=_name(db, deal.buyer_company_id),
        seller_company_id=deal.seller_company_id,
        seller_name=_name(db, deal.seller_company_id),
        funded_at=payment.funded_at,
        released_at=payment.released_at,
        refunded_at=payment.refunded_at,
        note=payment.note,
        provider_ref=payment.provider_ref,
        available_marks=[str(s) for s in escrow_service.available_marks(payment)],
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _blocked(db: Session) -> list[BlockedDealOut]:
    """Signed deals with no escrow and no amount to raise one from.

    The outbox consumer logs the blockage and moves on (raising would have the
    dispatcher retry forever), so this list is the only place staff can see it.
    """
    rows = (
        db.query(Deal)
        .outerjoin(EscrowPayment, EscrowPayment.deal_id == Deal.id)
        .filter(Deal.status == DealStatus.contract_signed, EscrowPayment.id.is_(None))
        .order_by(Deal.id.desc())
        .all()
    )
    return [
        BlockedDealOut(
            deal_id=deal.id,
            deal_number=deal.number,
            buyer_name=_name(db, deal.buyer_company_id),
            seller_name=_name(db, deal.seller_company_id),
            reason="no_amount" if deal.amount is None else "not_opened_yet",
            created_at=deal.created_at,
        )
        for deal in rows
    ]


# ── read ──────────────────────────────────────────────────────────────────────


@router.get("/escrow", response_model=EscrowListOut)
def list_escrow(
    escrow_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("escrow", "read")),
) -> EscrowListOut:
    query = db.query(EscrowPayment)
    if escrow_status:
        if escrow_status not in {s.value for s in EscrowStatus}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
            )
        query = query.filter(EscrowPayment.status == escrow_status)

    rows = query.order_by(EscrowPayment.id.desc()).limit(limit).offset(offset).all()
    items: list[EscrowPaymentOut] = []
    for payment in rows:
        deal = db.get(Deal, payment.deal_id)
        if deal is not None:  # pragma: no branch — FK guarantees it
            items.append(_out(db, payment, deal))

    # Counters describe the WHOLE board, not the filtered page: an operator
    # filtering to `funded` still needs to see how many payments are waiting.
    by_status = dict(
        db.query(EscrowPayment.status, func.count(EscrowPayment.id))
        .group_by(EscrowPayment.status)
        .all()
    )
    blocked = _blocked(db)
    return EscrowListOut(
        items=items,
        blocked=blocked,
        counters=EscrowCountersOut(
            awaiting_funds=by_status.get(EscrowStatus.pending, 0),
            awaiting_payout=by_status.get(EscrowStatus.funded, 0),
            settled=by_status.get(EscrowStatus.released, 0)
            + by_status.get(EscrowStatus.refunded, 0),
            blocked=len(blocked),
            provider_holds=len(escrow_service.held_provider_events(db)),
        ),
    )


@router.get("/escrow/provider-events", response_model=ProviderHoldListOut)
def list_provider_holds(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("escrow", "read")),
) -> ProviderHoldListOut:
    """Bank callbacks held for a human (R6 / P7.b).

    Declared BEFORE `/escrow/{payment_id}`: that route types the id as an int, so
    a literal segment declared after it would 422 rather than match.

    There is no resolve action here on purpose. Resolving a hold IS the ordinary
    mark on the payment — the operator checks the statement, disputes the deal if
    a refund is real, and marks it. The hold then stops being a disagreement and
    drops off this list by itself.
    """
    return ProviderHoldListOut(
        items=[ProviderHoldOut(**item) for item in escrow_service.held_provider_events(db, limit)]  # type: ignore[arg-type]
    )


@router.get("/escrow/{payment_id}", response_model=EscrowPaymentOut)
def get_escrow(
    payment_id: int,
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("escrow", "read")),
) -> EscrowPaymentOut:
    payment, deal = _payment_or_404(db, payment_id)
    return _out(db, payment, deal)


def _payment_or_404(db: Session, payment_id: int) -> tuple[EscrowPayment, Deal]:
    payment = db.get(EscrowPayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    deal = db.get(Deal, payment.deal_id)
    if deal is None:  # pragma: no cover — FK guarantees it
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return payment, deal


# ── mark (admin only) ─────────────────────────────────────────────────────────


@router.post("/escrow/{payment_id}/mark", response_model=EscrowPaymentOut)
def mark_escrow(
    payment_id: int,
    body: MarkIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("escrow", "write")),
) -> EscrowPaymentOut:
    """Record that money moved. The deal follows in the same transaction.

    Every refusal has its own reason, because "409" alone tells an operator
    holding a bank statement nothing about what to do next:
      * `invalid_transition` — the escrow machine says no (already released…),
      * `release_before_delivery` — the buyer has not confirmed delivery yet,
      * `deal_transition_blocked` — the deal cannot take the move; for a refund
        out of funded escrow that means it must be disputed first (FR-D8).
    """
    payment, _deal = _payment_or_404(db, payment_id)

    if not body.confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirmation_required"
        )
    if body.to_status not in {s.value for s in EscrowStatus}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
        )

    try:
        escrow_service.mark(
            db,
            payment,
            EscrowStatus(body.to_status),
            staff_user=staff,
            note=body.note,
        )
    except escrow_service.NoteRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="note_required"
        ) from exc
    except escrow_service.EscrowReleaseBeforeDelivery as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="release_before_delivery"
        ) from exc
    except escrow_service.InvalidEscrowTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid_transition"
        ) from exc
    except (deal_service.InvalidDealTransition, deal_service.ActorNotAllowed) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="deal_transition_blocked"
        ) from exc

    db.commit()
    db.refresh(payment)
    deal = db.get(Deal, payment.deal_id)
    assert deal is not None  # noqa: S101 — FK guarantees it; narrows the type
    db.refresh(deal)
    return _out(db, payment, deal)
