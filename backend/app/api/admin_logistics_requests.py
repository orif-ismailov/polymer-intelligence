"""Staff logistics-request oversight API. Under /api/v1/admin.

Read-only: analysts/admins list + inspect buyer→carrier logistics requests and
every carrier's thread on each. No staff mutation (no force-close/cancel) —
same shape as admin_contracts.py. This is a different board from the P6
`lab_orders`/`lab_partners` pipeline (admin_lab.py) and from `portal/logistics.py`
(which scopes a request to one carrier's own view) — this one is the whole board.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.models.companies import Company
from app.models.enums import LogisticsRequestStatus
from app.models.logistics import LogisticsRequest, LogisticsRequestMessage, LogisticsRequestThread
from app.models.staff import StaffUser
from app.services import logistics_service

router = APIRouter(prefix="/admin", tags=["admin-logistics-requests"])


class AdminLogisticsRequestOut(BaseModel):
    id: int
    public_id: uuid.UUID
    number: str
    status: str
    buyer_company_id: int
    buyer_name: str | None = None
    cargo_name: str
    volume: decimal.Decimal
    volume_unit: str
    packaging_type: str | None = None
    special_requirements: str | None = None
    from_country: str
    from_city: str | None = None
    to_country: str
    to_city: str | None = None
    contact_phone: str | None = None
    thread_count: int = 0
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AdminLogisticsThreadOut(BaseModel):
    id: int
    carrier_company_id: int
    carrier_name: str | None = None
    message_count: int = 0
    last_message_at: datetime.datetime | None = None
    last_message_preview: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AdminLogisticsRequestDetailOut(AdminLogisticsRequestOut):
    threads: list[AdminLogisticsThreadOut] = Field(default_factory=list)


def _company_name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, request: LogisticsRequest) -> AdminLogisticsRequestOut:
    thread_count = (
        db.query(LogisticsRequestThread)
        .filter(LogisticsRequestThread.logistics_request_id == request.id)
        .count()
    )
    return AdminLogisticsRequestOut(
        id=request.id,
        public_id=request.public_id,
        number=request.number,
        status=str(request.status),
        buyer_company_id=request.buyer_company_id,
        buyer_name=_company_name(db, request.buyer_company_id),
        cargo_name=request.cargo_name,
        volume=request.volume,
        volume_unit=request.volume_unit,
        packaging_type=request.packaging_type,
        special_requirements=request.special_requirements,
        from_country=request.from_country,
        from_city=request.from_city,
        to_country=request.to_country,
        to_city=request.to_city,
        contact_phone=request.contact_phone,
        thread_count=thread_count,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _thread_out(db: Session, thread: LogisticsRequestThread) -> AdminLogisticsThreadOut:
    message_count = (
        db.query(LogisticsRequestMessage)
        .filter(LogisticsRequestMessage.thread_id == thread.id)
        .count()
    )
    last = (
        db.query(LogisticsRequestMessage)
        .filter(LogisticsRequestMessage.thread_id == thread.id)
        .order_by(LogisticsRequestMessage.id.desc())
        .first()
    )
    preview: str | None = None
    if last is not None:
        preview = last.body[:140] if last.body else (f"[{last.file_name}]" if last.file_name else None)
    return AdminLogisticsThreadOut(
        id=thread.id,
        carrier_company_id=thread.carrier_company_id,
        carrier_name=_company_name(db, thread.carrier_company_id),
        message_count=message_count,
        last_message_at=last.created_at if last else None,
        last_message_preview=preview,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("/logistics-requests", response_model=list[AdminLogisticsRequestOut])
def list_logistics_requests(
    request_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> list[AdminLogisticsRequestOut]:
    stmt = select(LogisticsRequest)
    if request_status:
        if request_status not in {s.value for s in LogisticsRequestStatus}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bad status")
        stmt = stmt.where(LogisticsRequest.status == LogisticsRequestStatus(request_status))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(LogisticsRequest.number.ilike(like), LogisticsRequest.cargo_name.ilike(like))
        )
    stmt = stmt.order_by(LogisticsRequest.id.desc()).limit(200)
    return [_out(db, r) for r in db.execute(stmt).scalars().all()]


@router.get("/logistics-requests/{request_id}", response_model=AdminLogisticsRequestDetailOut)
def get_logistics_request(
    request_id: int,
    db: Session = Depends(get_db),
    _staff: StaffUser = Depends(require_analyst_or_admin),
) -> AdminLogisticsRequestDetailOut:
    request = db.get(LogisticsRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    base = _out(db, request)
    threads = logistics_service.list_threads_for_request(db, request.id)
    return AdminLogisticsRequestDetailOut(
        **base.model_dump(), threads=[_thread_out(db, t) for t in threads]
    )
