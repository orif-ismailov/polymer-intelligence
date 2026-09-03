"""Staff deal oversight API (R4 / P2 — T2.2). Under /api/v1/admin.

Staff see everything and touch almost nothing. The Trade Room is the parties'
own record, so there is deliberately no staff write path into the chat — only a
read endpoint for support and dispute work.

The one mutation is dispute resolution, and it is `require_admin`: an analyst
may read a dispute but not decide it. Resolution goes through
`deal_service.transition` like any other move, so it lands in the same timeline,
audit log and outbox — a staff decision is never invisible.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.deals import service as deal_service
from app.domains.deals.models import Deal, DealDocument, DealMessage, DealStatusHistory
from app.models.enums import DealActorKind, DealStatus
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin", tags=["admin-deals"])


# ── schemas ───────────────────────────────────────────────────────────────────


class AdminTimelineOut(BaseModel):
    id: int
    from_status: str | None = None
    to_status: str
    actor_kind: str
    actor_id: int | None = None
    reason: str | None = None
    created_at: datetime.datetime


class AdminDealDocumentOut(BaseModel):
    id: int
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by_company_id: int
    revoked: bool
    revoked_reason: str | None = None
    created_at: datetime.datetime


class AdminDealOut(BaseModel):
    id: int
    public_id: uuid.UUID
    number: str
    status: str
    buyer_company_id: int
    buyer_name: str | None = None
    seller_company_id: int
    seller_name: str | None = None
    amount: decimal.Decimal | None = None
    currency: str
    contract_id: int | None = None
    request_id: int | None = None
    offer_id: int | None = None
    cancelled_reason: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("amount")
    def _amount(self, value: decimal.Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class AdminDealListOut(BaseModel):
    items: list[AdminDealOut]
    total: int


class AdminDealDetailOut(AdminDealOut):
    timeline: list[AdminTimelineOut] = Field(default_factory=list)
    documents: list[AdminDealDocumentOut] = Field(default_factory=list)
    message_count: int = 0


class AdminMessageOut(BaseModel):
    id: int
    body: str
    file_name: str | None = None
    has_file: bool = False
    author_account_id: int
    author_company_id: int
    author_company_name: str | None = None
    created_at: datetime.datetime


class AdminMessagePageOut(BaseModel):
    items: list[AdminMessageOut]
    last_id: int | None = None


class ResolveDisputeIn(BaseModel):
    #: 'cancel' ends the deal; 'restore' puts it back to a pre-dispute status.
    action: str = Field(pattern="^(cancel|restore)$")
    restore_to: str | None = None
    comment: str = Field(min_length=1, max_length=1000)


# ── helpers ───────────────────────────────────────────────────────────────────


def _name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, deal: Deal) -> AdminDealOut:
    return AdminDealOut(
        id=deal.id,
        public_id=deal.public_id,
        number=deal.number,
        status=str(deal.status),
        buyer_company_id=deal.buyer_company_id,
        buyer_name=_name(db, deal.buyer_company_id),
        seller_company_id=deal.seller_company_id,
        seller_name=_name(db, deal.seller_company_id),
        amount=deal.amount,
        currency=deal.currency,
        contract_id=deal.contract_id,
        request_id=deal.request_id,
        offer_id=deal.offer_id,
        cancelled_reason=deal.cancelled_reason,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
    )


def _detail(db: Session, deal: Deal) -> AdminDealDetailOut:
    history = (
        db.query(DealStatusHistory)
        .filter(DealStatusHistory.deal_id == deal.id)
        .order_by(DealStatusHistory.id)
        .all()
    )
    documents = (
        db.query(DealDocument)
        .filter(DealDocument.deal_id == deal.id)
        .order_by(DealDocument.id)
        .all()
    )
    return AdminDealDetailOut(
        **_out(db, deal).model_dump(),
        timeline=[
            AdminTimelineOut(
                id=h.id,
                from_status=str(h.from_status) if h.from_status else None,
                to_status=str(h.to_status),
                actor_kind=str(h.actor_kind),
                actor_id=h.actor_id,
                reason=h.reason,
                created_at=h.created_at,
            )
            for h in history
        ],
        documents=[
            AdminDealDocumentOut(
                id=d.id,
                kind=str(d.kind),
                file_name=d.file_name,
                mime_type=d.mime_type,
                size_bytes=d.size_bytes,
                sha256=d.sha256,
                uploaded_by_company_id=d.uploaded_by_company_id,
                revoked=d.revoked,
                revoked_reason=d.revoked_reason,
                created_at=d.created_at,
            )
            for d in documents
        ],
        message_count=db.query(DealMessage).filter(DealMessage.deal_id == deal.id).count(),
    )


def _deal_or_404(db: Session, deal_id: int) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return deal


# ── read ──────────────────────────────────────────────────────────────────────


@router.get("/deals", response_model=AdminDealListOut)
def list_deals(
    deal_status: str | None = Query(default=None, alias="status"),
    q: str = Query(default="", max_length=200),
    company_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("deals", "read")),
) -> AdminDealListOut:
    query = db.query(Deal)
    if deal_status:
        if deal_status not in {s.value for s in DealStatus}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
            )
        query = query.filter(Deal.status == deal_status)
    if company_id is not None:
        query = query.filter(
            or_(Deal.buyer_company_id == company_id, Deal.seller_company_id == company_id)
        )
    term = q.strip()
    if term:
        query = query.filter(Deal.number.ilike(f"%{term}%"))

    total = query.count()
    rows = query.order_by(Deal.id.desc()).limit(limit).offset(offset).all()
    return AdminDealListOut(items=[_out(db, d) for d in rows], total=total)


@router.get("/deals/{deal_id}", response_model=AdminDealDetailOut)
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("deals", "read")),
) -> AdminDealDetailOut:
    return _detail(db, _deal_or_404(db, deal_id))


@router.get("/deals/{deal_id}/messages", response_model=AdminMessagePageOut)
def list_deal_messages(
    deal_id: int,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_page("deals", "read")),
) -> AdminMessagePageOut:
    """Read-only view of the Trade Room chat (support + dispute context)."""
    deal = _deal_or_404(db, deal_id)
    rows = deal_service.list_messages(db, deal, after_id=after_id, limit=limit)
    return AdminMessagePageOut(
        items=[
            AdminMessageOut(
                id=m.id,
                body=m.body,
                file_name=m.file_name,
                has_file=m.file_storage_path is not None,
                author_account_id=m.author_account_id,
                author_company_id=m.author_company_id,
                author_company_name=_name(db, m.author_company_id),
                created_at=m.created_at,
            )
            for m in rows
        ],
        last_id=rows[-1].id if rows else after_id,
    )


# ── dispute resolution (admin only) ───────────────────────────────────────────


@router.post("/deals/{deal_id}/resolve-dispute", response_model=AdminDealDetailOut)
def resolve_dispute(
    deal_id: int,
    body: ResolveDisputeIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_page("deals", "write")),
) -> AdminDealDetailOut:
    """Cancel a disputed deal or restore it to a pre-dispute status.

    `restore_to` is validated by the state machine, not by this handler: only
    the statuses a dispute can be entered from are reachable, so staff cannot
    use dispute resolution to teleport a deal to `completed`.
    """
    deal = _deal_or_404(db, deal_id)
    if deal.status != DealStatus.disputed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_disputed")

    if body.action == "cancel":
        target = DealStatus.cancelled
    else:
        if not body.restore_to or body.restore_to not in {s.value for s in DealStatus}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="restore_to_required"
            )
        target = DealStatus(body.restore_to)

    try:
        deal_service.transition(
            db,
            deal,
            target,
            actor_kind=DealActorKind.staff,
            actor_id=staff.id,
            reason=body.comment,
        )
    except deal_service.InvalidDealTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid_transition"
        ) from exc
    except deal_service.ActorNotAllowed as exc:  # pragma: no cover — staff always may
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="actor_not_allowed"
        ) from exc

    from app.services.audit_service import write_audit  # noqa: PLC0415

    write_audit(
        db, staff.id, "deal.resolve_dispute", "deals", str(deal.id),
        {"action": body.action, "to": target.value, "comment": body.comment},
    )
    db.commit()
    db.refresh(deal)
    return _detail(db, deal)
