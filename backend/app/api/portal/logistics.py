"""Logistics service requests (cabinet).

A buyer opens a carrier's PUBLIC profile, taps «Связаться с компанией» and fills
one short form. Reading a carrier is anonymous (`/api/v1/public/directories/
logistics`); acting on one is not — every route here requires a portal session
AND an active membership in the company doing the asking, the same bar the
factory RFQ sets.

Route order matters: `/requests` and `/requests/{id}` are declared BEFORE
`/{logistics_id}/requests`, because both match `/portal/logistics/X/Y` and
FastAPI resolves first-registered. `test_portal_logistics_api` pins the literal
paths so a reorder fails there rather than in production.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.logistics import LogisticsRequest
from app.schemas.portal_logistics import (
    LogisticsRequestCreateIn,
    LogisticsRequestListOut,
    LogisticsRequestOut,
)
from app.services import company_service, logistics_service, notification_service

router = APIRouter(prefix="/portal/logistics", tags=["portal-logistics"])


def _company_or_404(db: Session, account: UserAccount, company_id: int) -> Company:
    try:
        return company_service.get_company_for(db, account, company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc


def _request_out(db: Session, request: LogisticsRequest) -> LogisticsRequestOut:
    buyer = db.get(Company, request.buyer_company_id)
    carrier = db.get(Company, request.logistics_company_id)
    return LogisticsRequestOut(
        id=request.id,
        public_id=request.public_id,
        number=request.number,
        buyer_company_id=request.buyer_company_id,
        logistics_company_id=request.logistics_company_id,
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
        status=str(request.status),
        created_at=request.created_at,
        buyer_name=(buyer.short_name or buyer.legal_name) if buyer else None,
        logistics_name=(carrier.short_name or carrier.legal_name) if carrier else None,
    )


@router.get("/requests", response_model=LogisticsRequestListOut, summary="List logistics requests")
def list_requests(
    company_id: int = Query(...),
    side: str = Query(default="sent", pattern="^(sent|incoming)$"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsRequestListOut:
    """GET /portal/logistics/requests — this company's sent or incoming requests."""
    company = _company_or_404(db, account, company_id)
    rows = logistics_service.list_logistics_requests_for(db, company.id, side=side)
    return LogisticsRequestListOut(items=[_request_out(db, r) for r in rows])


@router.get(
    "/requests/{request_id}",
    response_model=LogisticsRequestOut,
    summary="One logistics request",
)
def get_request(
    request_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsRequestOut:
    """GET /portal/logistics/requests/{id} — visible to either party only."""
    try:
        request = logistics_service.get_logistics_request_for(
            db, account, request_id, company_id
        )
    except logistics_service.NotLogisticsParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc
    return _request_out(db, request)


@router.post(
    "/{logistics_id}/requests",
    response_model=LogisticsRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a logistics request to a carrier",
)
def create_request(
    logistics_id: int,
    body: LogisticsRequestCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsRequestOut:
    """POST /portal/logistics/{id}/requests — «Отправить заявку»."""
    buyer = _company_or_404(db, account, body.company_id)
    try:
        carrier = logistics_service.get_verified_logistics_company(db, logistics_id)
    except logistics_service.LogisticsCompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Logistics company not found"
        ) from exc

    try:
        request = logistics_service.create_logistics_request(
            db,
            buyer=buyer,
            carrier=carrier,
            account=account,
            cargo_name=body.cargo_name,
            volume=body.volume,
            volume_unit=body.volume_unit,
            packaging_type=body.packaging_type,
            special_requirements=body.special_requirements,
            from_country=body.from_country,
            from_city=body.from_city,
            to_country=body.to_country,
            to_city=body.to_city,
        )
    except logistics_service.SelfLogisticsRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="self_logistics_request",
        ) from exc

    # Inside the same transaction as the insert: a request the carrier is never
    # told about is a request nobody answers, so the two commit together or not
    # at all. `exclude_account_id` is moot here (the sender is on the other
    # company) but passed for the same reason every other producer passes it.
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LOGISTICS_REQUEST_NEW
    )
    notification_service.notify_company(
        db,
        carrier.id,
        kind=notification_service.KIND_LOGISTICS_REQUEST_NEW,
        title_key=title_key,
        body_key=body_key,
        params={
            "request_id": request.id,
            "number": request.number,
            "cargo": request.cargo_name,
            "buyer": buyer.short_name or buyer.legal_name or "",
        },
        entity="logistics_request",
        entity_id=str(request.id),
        exclude_account_id=account.id,
    )

    db.commit()
    db.refresh(request)
    return _request_out(db, request)
