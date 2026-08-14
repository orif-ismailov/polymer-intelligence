"""Staff lab-request oversight API. Under /api/v1/admin.

Read-only: analysts/admins list + inspect buyer→laboratory analysis requests and
every laboratory's thread on each. No staff mutation (no force-close/cancel) —
same shape as admin_contracts.py / admin_logistics_requests.py. NOT the P6
`lab_orders`/`lab_partners` pipeline (admin_lab.py) — that one is a separate,
staff-run manual-QC-analysis process. This is the buyer↔laboratory-company
broadcast board, route `/admin/lab-requests`.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.laboratory import service as laboratory_service
from app.domains.laboratory.models import LabRequest, LabRequestMessage, LabRequestThread
from app.models.enums import LabRequestStatus

router = APIRouter(prefix="/admin", tags=["admin-lab-requests"], dependencies=[Depends(require_analyst_or_admin)])


class AdminLabRequestOut(BaseModel):
    id: int
    public_id: uuid.UUID
    number: str
    status: str
    buyer_company_id: int
    buyer_name: str | None = None
    product_id: int | None = None
    product_text: str
    grade_text: str | None = None
    study_type: str | None = None
    methods: list[str] = Field(default_factory=list)
    sample_qty: str | None = None
    comment: str | None = None
    purpose: str | None = None
    is_urgent: bool = False
    desired_date: datetime.date | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    thread_count: int = 0
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AdminLabThreadOut(BaseModel):
    id: int
    laboratory_company_id: int
    laboratory_name: str | None = None
    message_count: int = 0
    last_message_at: datetime.datetime | None = None
    last_message_preview: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AdminLabRequestDetailOut(AdminLabRequestOut):
    threads: list[AdminLabThreadOut] = Field(default_factory=list)


def _company_name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, request: LabRequest) -> AdminLabRequestOut:
    thread_count = (
        db.query(LabRequestThread).filter(LabRequestThread.lab_request_id == request.id).count()
    )
    return AdminLabRequestOut(
        id=request.id,
        public_id=request.public_id,
        number=request.number,
        status=str(request.status),
        buyer_company_id=request.buyer_company_id,
        buyer_name=_company_name(db, request.buyer_company_id),
        product_id=request.product_id,
        product_text=request.product_text,
        grade_text=request.grade_text,
        study_type=request.study_type,
        methods=request.methods or [],
        sample_qty=request.sample_qty,
        comment=request.comment,
        purpose=request.purpose,
        is_urgent=request.is_urgent,
        desired_date=request.desired_date,
        contact_name=request.contact_name,
        contact_email=request.contact_email,
        contact_phone=request.contact_phone,
        thread_count=thread_count,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _thread_out(db: Session, thread: LabRequestThread) -> AdminLabThreadOut:
    message_count = (
        db.query(LabRequestMessage).filter(LabRequestMessage.thread_id == thread.id).count()
    )
    last = (
        db.query(LabRequestMessage)
        .filter(LabRequestMessage.thread_id == thread.id)
        .order_by(LabRequestMessage.id.desc())
        .first()
    )
    preview: str | None = None
    if last is not None:
        preview = last.body[:140] if last.body else (f"[{last.file_name}]" if last.file_name else None)
    return AdminLabThreadOut(
        id=thread.id,
        laboratory_company_id=thread.laboratory_company_id,
        laboratory_name=_company_name(db, thread.laboratory_company_id),
        message_count=message_count,
        last_message_at=last.created_at if last else None,
        last_message_preview=preview,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("/lab-requests", response_model=list[AdminLabRequestOut])
def list_lab_requests(
    request_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> list[AdminLabRequestOut]:
    stmt = select(LabRequest)
    if request_status:
        if request_status not in {s.value for s in LabRequestStatus}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bad status")
        stmt = stmt.where(LabRequest.status == LabRequestStatus(request_status))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(LabRequest.number.ilike(like), LabRequest.product_text.ilike(like))
        )
    stmt = stmt.order_by(LabRequest.id.desc()).limit(200)
    return [_out(db, r) for r in db.execute(stmt).scalars().all()]


@router.get("/lab-requests/{request_id}", response_model=AdminLabRequestDetailOut)
def get_lab_request(
    request_id: int,
    db: Session = Depends(get_db),
) -> AdminLabRequestDetailOut:
    request = db.get(LabRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    base = _out(db, request)
    threads = laboratory_service.list_threads_for_request(db, request.id)
    return AdminLabRequestDetailOut(
        **base.model_dump(), threads=[_thread_out(db, t) for t in threads]
    )
