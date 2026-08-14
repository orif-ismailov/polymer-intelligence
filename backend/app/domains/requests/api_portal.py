"""Portal purchase-request endpoints (R2 W3 T3.3). Under /api/v1/portal.

A buyer, acting for a selected company, creates purchase requests through the same
wizard payload as the Mini App. The request enters the SAME status machine +
history and appears in the dashboard `/requests` identically to TG-originated ones.
The read side reuses the webapp RequestOut/RequestDetailOut (raw status; the portal
maps to client-facing labels), so a portal request serializes like a TG request.

Company-scoped: every route carries company_id; membership is enforced (non-member
→ 404 = no cross-company disclosure).
"""

from __future__ import annotations

import redis
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, rate_limited, require_business_role
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.requests import service as request_service
from app.domains.requests.models import Request
from app.domains.requests.schemas import PortalRequestCreate
from app.domains.requests.webapp_schemas import RequestDetailOut, RequestFileOut, RequestOut
from app.services import rate_limit, storage_service

router = APIRouter(prefix="/portal/requests", tags=["portal-requests"])

_MAX_FILES = 5


def _request_or_404(db: Session, company_id: int, request_id: int) -> Request:
    req = request_service.get_company_request(db, company_id, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return req


@router.post(
    "",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase request (as a company)",
)
def create_request(
    body: PortalRequestCreate,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),
) -> RequestOut:
    company = company_or_404(db, account, body.company_id)
    require_business_role(company, company_service.BUYER_CAPABLE_ROLES)
    try:
        rate_limit.enforce_daily(
            redis_client, "request_create", company.id, rate_limit.REQUEST_CREATE_PER_DAY
        )
    except rate_limit.RateLimited as exc:
        raise rate_limited(exc) from exc
    req = request_service.create_company_request(db, company, account, body)
    db.commit()
    return RequestOut.model_validate(req)


@router.post(
    "/{request_id}/files",
    response_model=RequestFileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a file to a request",
)
def upload_file(
    request_id: int,
    company_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RequestFileOut:
    company = company_or_404(db, account, company_id)
    req = _request_or_404(db, company.id, request_id)
    if len(req.files or []) >= _MAX_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Too many files")
    content = file.file.read()
    try:
        rf = storage_service.upload_request_file(db, req.id, content, file.filename or "file")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    return RequestFileOut.model_validate(rf)


@router.get("", response_model=list[RequestOut], summary="List my company's requests")
def list_requests(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[RequestOut]:
    company = company_or_404(db, account, company_id)
    rows = request_service.list_company_requests(db, company.id)
    return [RequestOut.model_validate(r) for r in rows]


@router.get(
    "/{request_id}",
    response_model=RequestDetailOut,
    summary="Request detail + status timeline",
)
def get_request(
    request_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RequestDetailOut:
    company = company_or_404(db, account, company_id)
    req = _request_or_404(db, company.id, request_id)
    history = sorted(req.status_history, key=lambda h: h.created_at)
    return RequestDetailOut(
        id=req.id,
        number=req.number,
        status=req.status,
        created_at=req.created_at,
        product_id=req.product_id,
        product_text=req.product_text,
        grade_text=req.grade_text,
        polymer_type=req.polymer_type,
        volume=req.volume,
        volume_unit=req.volume_unit,
        target_price=req.target_price,
        currency=req.currency,
        incoterms=req.incoterms,
        destination_country=req.destination_country,
        port_or_city=req.port_or_city,
        desired_date=req.desired_date,
        validity_days=req.validity_days,
        urgency=req.urgency,
        comment=req.comment,
        company_name=req.company_name,
        contact_name=req.contact_name,
        phone=req.phone,
        legal_address=req.legal_address,
        files=req.files,
        history=history,
    )


@router.post(
    "/{request_id}/cancel",
    response_model=RequestOut,
    summary="Cancel a request (client-visible non-terminal states)",
)
def cancel_request(
    request_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RequestOut:
    company = company_or_404(db, account, company_id)
    req = _request_or_404(db, company.id, request_id)
    try:
        request_service.cancel_request(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return RequestOut.model_validate(req)
