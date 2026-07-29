"""Portal deal endpoints (R4 / P2 — T2.1). Under /api/v1.

Everything here is company-scoped: the `company_id` in the path is the hat the
caller is wearing, and it decides which side of a deal they act as. Access is
two-tiered, matching the rest of the portal —

  * READ: any active member of a party company (`get_company_for`, which 404s
    for outsiders so a deal's existence never leaks),
  * ACT: owner/manager only (`deal_service.acting_company`) — a plain member can
    follow a Trade Room but not speak or transition for the company.

A third company gets 404, never 403: a 403 would confirm the deal exists.
"""

from __future__ import annotations

import decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.contracts import Contract
from app.models.deals import Deal, DealDocument, DealMessage, DealStatusHistory, RfqResponse
from app.models.enums import (
    CompanyStatus,
    DealDocumentKind,
    DealStatus,
    PriceBasis,
    RfqResponseStatus,
)
from app.models.requests import Request
from app.schemas.portal_deal import (
    DealCountersOut,
    DealDetailOut,
    DealDocumentOut,
    DealEscrowOut,
    DealListOut,
    DealMessageOut,
    DealMessagePageOut,
    DealSummaryOut,
    MarketRequestListOut,
    MarketRequestOut,
    PartyOut,
    RevokeIn,
    RfqResponseIn,
    RfqResponseListOut,
    RfqResponseOut,
    TimelineEntryOut,
    TransitionIn,
)
from app.services import (
    company_service,
    deal_service,
    escrow_service,
    rfq_response_service,
    storage_service,
)

router = APIRouter(prefix="/portal", tags=["portal-deals"])


# ── loaders ───────────────────────────────────────────────────────────────────


def _company_or_404(db: Session, account: UserAccount, company_id: int) -> Company:
    try:
        return company_service.get_company_for(db, account, company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc


def _deal_or_404(db: Session, company: Company, deal_id: int) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None or company.id not in (deal.buyer_company_id, deal.seller_company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return deal


def _acting_or_403(db: Session, deal: Deal, account: UserAccount, company: Company) -> Company:
    """The caller must be an owner/manager of THIS company to act."""
    try:
        return deal_service.acting_company(db, deal, account, company.id)
    except deal_service.NotDealParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role"
        ) from exc


def _request_or_404(db: Session, request_id: int) -> Request:
    request = db.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


# ── serializers ───────────────────────────────────────────────────────────────


def _party(db: Session, company_id: int) -> PartyOut:
    company = db.get(Company, company_id)
    if company is None:  # pragma: no cover — FK guarantees it
        return PartyOut(company_id=company_id)
    return PartyOut(
        company_id=company.id,
        name=company.legal_name or company.short_name or company.tax_id,
        logo_url=storage_service.presign_company_logo(company, ttl=600),
        verified=company.status == CompanyStatus.verified,
        roles=[str(r.role) for r in company.business_roles],
    )


def _summary(db: Session, deal: Deal, company_id: int) -> DealSummaryOut:
    role = deal.party_role(company_id) or "buyer"
    other = deal.seller_company_id if role == "buyer" else deal.buyer_company_id
    actor = deal_service.actor_kind_for(deal, db.get(Company, company_id))  # type: ignore[arg-type]
    return DealSummaryOut(
        id=deal.id,
        public_id=deal.public_id,
        number=deal.number,
        status=str(deal.status),
        role=role,
        counterparty=_party(db, other),
        amount=deal.amount,
        currency=deal.currency,
        contract_id=deal.contract_id,
        needs_action=deal_service.needs_action(deal, actor),
        created_at=deal.created_at,
        updated_at=deal.updated_at,
    )


def _detail(db: Session, deal: Deal, company_id: int) -> DealDetailOut:
    base = _summary(db, deal, company_id)
    actor = deal_service.actor_kind_for(deal, db.get(Company, company_id))  # type: ignore[arg-type]
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
    contract_status: str | None = None
    if deal.contract_id is not None:
        contract = db.get(Contract, deal.contract_id)
        contract_status = str(contract.status) if contract is not None else None

    # Both sides see the same escrow block: the whole point of escrow is that
    # each party can see where the money is without asking the other.
    payment = escrow_service.for_deal(db, deal.id)
    escrow = (
        None
        if payment is None
        else DealEscrowOut(
            status=str(payment.status),
            amount=payment.amount,
            currency=payment.currency,
            funded_at=payment.funded_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
        )
    )

    return DealDetailOut(
        **base.model_dump(),
        buyer=_party(db, deal.buyer_company_id),
        seller=_party(db, deal.seller_company_id),
        request_id=deal.request_id,
        offer_id=deal.offer_id,
        contract_status=contract_status,
        cancelled_reason=deal.cancelled_reason,
        timeline=[
            TimelineEntryOut(
                id=h.id,
                from_status=str(h.from_status) if h.from_status else None,
                to_status=str(h.to_status),
                actor_kind=str(h.actor_kind),
                reason=h.reason,
                created_at=h.created_at,
            )
            for h in history
        ],
        documents=[_document(db, d) for d in documents],
        available_transitions=[
            str(s) for s in deal_service.available_transitions(deal, actor)
        ],
        escrow=escrow,
    )


def _document(db: Session, document: DealDocument) -> DealDocumentOut:
    company = db.get(Company, document.uploaded_by_company_id)
    return DealDocumentOut(
        id=document.id,
        kind=str(document.kind),
        file_name=document.file_name,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        uploaded_by_company_id=document.uploaded_by_company_id,
        uploaded_by_company_name=(
            company.legal_name or company.short_name or company.tax_id if company else None
        ),
        revoked=document.revoked,
        revoked_reason=document.revoked_reason,
        created_at=document.created_at,
    )


def _message(db: Session, message: DealMessage, company_id: int) -> DealMessageOut:
    company = db.get(Company, message.author_company_id)
    return DealMessageOut(
        id=message.id,
        body=message.body,
        file_name=message.file_name,
        has_file=message.file_storage_path is not None,
        author_account_id=message.author_account_id,
        author_company_id=message.author_company_id,
        author_company_name=(
            company.legal_name or company.short_name or company.tax_id if company else None
        ),
        mine=message.author_company_id == company_id,
        created_at=message.created_at,
    )


def _response_out(db: Session, response: RfqResponse) -> RfqResponseOut:
    company = db.get(Company, response.company_id)
    return RfqResponseOut(
        id=response.id,
        request_id=response.request_id,
        company_id=response.company_id,
        company_name=(
            company.legal_name or company.short_name or company.tax_id if company else None
        ),
        company_verified=company.status == CompanyStatus.verified if company else False,
        price=response.price,
        currency=response.currency,
        qty=response.qty,
        qty_unit=response.qty_unit,
        incoterms=str(response.incoterms) if response.incoterms else None,
        lead_time_days=response.lead_time_days,
        comment=response.comment,
        status=str(response.status),
        deal_id=response.deal_id,
        created_at=response.created_at,
    )


# ── deals ─────────────────────────────────────────────────────────────────────


@router.get("/companies/{company_id}/deals", response_model=DealListOut)
def list_deals(
    company_id: int,
    role: str | None = Query(default=None, pattern="^(buyer|seller)$"),
    deal_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealListOut:
    company = _company_or_404(db, account, company_id)
    query = db.query(Deal).filter(
        or_(Deal.buyer_company_id == company.id, Deal.seller_company_id == company.id)
    )
    if role == "buyer":
        query = query.filter(Deal.buyer_company_id == company.id)
    elif role == "seller":
        query = query.filter(Deal.seller_company_id == company.id)
    if deal_status:
        if deal_status not in {s.value for s in DealStatus}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
            )
        query = query.filter(Deal.status == deal_status)

    items = [_summary(db, d, company.id) for d in query.order_by(Deal.id.desc()).all()]
    closed = {DealStatus.completed.value, DealStatus.cancelled.value}
    return DealListOut(
        items=items,
        counters=DealCountersOut(
            total=len(items),
            needs_action=sum(1 for i in items if i.needs_action),
            active=sum(1 for i in items if i.status not in closed),
            closed=sum(1 for i in items if i.status in closed),
        ),
    )


@router.get("/companies/{company_id}/deals/{deal_id}", response_model=DealDetailOut)
def get_deal(
    company_id: int,
    deal_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealDetailOut:
    company = _company_or_404(db, account, company_id)
    return _detail(db, _deal_or_404(db, company, deal_id), company.id)


@router.post("/companies/{company_id}/deals/{deal_id}/transition", response_model=DealDetailOut)
def transition_deal(
    company_id: int,
    deal_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealDetailOut:
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    _acting_or_403(db, deal, account, company)

    if body.to_status not in {s.value for s in DealStatus}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
        )
    try:
        deal_service.transition_by_party(
            db, deal, account, DealStatus(body.to_status), body.reason, company_id=company.id
        )
    except deal_service.ReasonRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reason_required"
        ) from exc
    except deal_service.ActorNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="actor_not_allowed"
        ) from exc
    except deal_service.InvalidDealTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid_transition"
        ) from exc
    db.commit()
    db.refresh(deal)
    return _detail(db, deal, company.id)


# ── chat ──────────────────────────────────────────────────────────────────────


@router.get(
    "/companies/{company_id}/deals/{deal_id}/messages", response_model=DealMessagePageOut
)
def list_deal_messages(
    company_id: int,
    deal_id: int,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealMessagePageOut:
    """Chat page. Poll with `after_id` = the previous `last_id` for the delta only."""
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    rows = deal_service.list_messages(db, deal, after_id=after_id, limit=limit)
    return DealMessagePageOut(
        items=[_message(db, m, company.id) for m in rows],
        last_id=rows[-1].id if rows else after_id,
    )


@router.post(
    "/companies/{company_id}/deals/{deal_id}/messages",
    response_model=DealMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_deal_message(
    company_id: int,
    deal_id: int,
    body: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealMessageOut:
    """Post a message. Multipart always, so text and file take one code path."""
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    _acting_or_403(db, deal, account, company)

    content = await file.read() if file is not None else None
    try:
        message = deal_service.post_message(
            db,
            deal,
            account,
            body,
            file_content=content,
            file_name=file.filename if file is not None else None,
            company_id=company.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(message)
    return _message(db, message, company.id)


@router.get("/companies/{company_id}/deals/{deal_id}/messages/{message_id}/file")
def get_deal_message_file(
    company_id: int,
    deal_id: int,
    message_id: int,
    as_: str = Query(default="redirect", alias="as"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Presigned link to a chat attachment (TTL ≤ 600 s)."""
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    message = (
        db.query(DealMessage)
        .filter(DealMessage.id == message_id, DealMessage.deal_id == deal.id)
        .first()
    )
    if message is None or not message.file_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No file")
    url = storage_service.presign_object(message.file_storage_path, ttl=600)
    if as_ == "url":
        return JSONResponse({"url": url})
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# ── documents ─────────────────────────────────────────────────────────────────


@router.post(
    "/companies/{company_id}/deals/{deal_id}/documents",
    response_model=DealDocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_deal_document(
    company_id: int,
    deal_id: int,
    kind: str = Form(default="other"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealDocumentOut:
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    _acting_or_403(db, deal, account, company)

    if kind not in {k.value for k in DealDocumentKind}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_kind"
        )
    content = await file.read()
    try:
        document = deal_service.add_document(
            db,
            deal,
            account,
            DealDocumentKind(kind),
            content,
            file.filename or "upload",
            company_id=company.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(document)
    return _document(db, document)


@router.get("/companies/{company_id}/deals/{deal_id}/documents/{document_id}")
def get_deal_document(
    company_id: int,
    deal_id: int,
    document_id: int,
    as_: str = Query(default="redirect", alias="as"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Presigned link to a deal document (TTL ≤ 600 s). Both parties may read."""
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    document = (
        db.query(DealDocument)
        .filter(DealDocument.id == document_id, DealDocument.deal_id == deal.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    url = storage_service.presign_object(document.storage_path, ttl=600)
    if as_ == "url":
        return JSONResponse({"url": url})
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post(
    "/companies/{company_id}/deals/{deal_id}/documents/{document_id}/revoke",
    response_model=DealDocumentOut,
)
def revoke_deal_document(
    company_id: int,
    deal_id: int,
    document_id: int,
    body: RevokeIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealDocumentOut:
    company = _company_or_404(db, account, company_id)
    deal = _deal_or_404(db, company, deal_id)
    document = (
        db.query(DealDocument)
        .filter(DealDocument.id == document_id, DealDocument.deal_id == deal.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        deal_service.revoke_document(db, document, account, body.reason, company_id=company.id)
    except deal_service.NotDealParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not_the_uploader"
        ) from exc
    except deal_service.DocumentAlreadyRevoked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="already_revoked"
        ) from exc
    db.commit()
    db.refresh(document)
    return _document(db, document)


# ── RFQ responses ─────────────────────────────────────────────────────────────


@router.post(
    "/companies/{company_id}/requests/{request_id}/responses",
    response_model=RfqResponseOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_rfq_response(
    company_id: int,
    request_id: int,
    body: RfqResponseIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RfqResponseOut:
    """Quote against a buyer's RFQ on behalf of this supplier company."""
    company = _company_or_404(db, account, company_id)
    company_service.require_company_role(
        db, account, company.id, company_service.COMPANY_ADMIN_ROLES
    )
    request = _request_or_404(db, request_id)

    incoterms: PriceBasis | None = None
    if body.incoterms:
        if body.incoterms not in {p.value for p in PriceBasis}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_incoterms"
            )
        incoterms = PriceBasis(body.incoterms)

    try:
        response = rfq_response_service.submit(
            db, request, company, account,
            price=body.price, currency=body.currency, qty=body.qty, qty_unit=body.qty_unit,
            incoterms=incoterms, lead_time_days=body.lead_time_days, comment=body.comment,
        )
    except rfq_response_service.AlreadyResponded as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="already_responded"
        ) from exc
    except rfq_response_service.CannotRespondOwnRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="own_request"
        ) from exc
    except rfq_response_service.RfqNotVisible as exc:
        # 404, not 403: a supplier outside the allow-list must not learn the RFQ exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        ) from exc
    except rfq_response_service.RequestNotOpen as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="request_closed") from exc
    except deal_service.CompanyNotVerified as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_not_verified"
        ) from exc
    db.commit()
    db.refresh(response)
    return _response_out(db, response)


@router.get(
    "/companies/{company_id}/requests/{request_id}/responses",
    response_model=RfqResponseListOut,
)
def list_rfq_responses(
    company_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RfqResponseListOut:
    """The RFQ owner sees every quote; a supplier sees only their own."""
    company = _company_or_404(db, account, company_id)
    request = _request_or_404(db, request_id)

    is_owner = request.company_id == company.id
    if not is_owner and not rfq_response_service.is_visible_to(request, company):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    rows = rfq_response_service.list_for_request(
        db, request, viewer_company_id=None if is_owner else company.id
    )
    return RfqResponseListOut(items=[_response_out(db, r) for r in rows])


@router.post(
    "/companies/{company_id}/requests/{request_id}/responses/{response_id}/accept",
    response_model=DealDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def accept_rfq_response(
    company_id: int,
    request_id: int,
    response_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> DealDetailOut:
    """Accept a quote — opens the Deal and retires the competing responses."""
    company = _company_or_404(db, account, company_id)
    company_service.require_company_role(
        db, account, company.id, company_service.COMPANY_ADMIN_ROLES
    )
    request = _request_or_404(db, request_id)
    if request.company_id != company.id:
        # Only the buyer accepts. Anyone else must not learn this RFQ exists here.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    response = (
        db.query(RfqResponse)
        .filter(RfqResponse.id == response_id, RfqResponse.request_id == request.id)
        .first()
    )
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Response not found")

    try:
        deal = deal_service.open_deal_from_response(db, request, response, account)
    except deal_service.ResponseAlreadyAccepted as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="already_accepted"
        ) from exc
    except deal_service.ResponseNotOpen as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="response_closed") from exc
    except deal_service.CompanyNotVerified as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_not_verified"
        ) from exc
    except deal_service.DealRequiresCompany as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_required"
        ) from exc
    db.commit()
    db.refresh(deal)
    return _detail(db, deal, company.id)


@router.post(
    "/companies/{company_id}/requests/{request_id}/responses/{response_id}/withdraw",
    response_model=RfqResponseOut,
)
def withdraw_rfq_response(
    company_id: int,
    request_id: int,
    response_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> RfqResponseOut:
    company = _company_or_404(db, account, company_id)
    response = (
        db.query(RfqResponse)
        .filter(
            RfqResponse.id == response_id,
            RfqResponse.request_id == request_id,
            RfqResponse.company_id == company.id,
        )
        .first()
    )
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Response not found")
    try:
        rfq_response_service.withdraw(db, response, account)
    except rfq_response_service.NotResponseAuthor as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_author") from exc
    except deal_service.ResponseNotOpen as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="response_closed") from exc
    db.commit()
    db.refresh(response)
    return _response_out(db, response)


# ── supplier-facing RFQ market ────────────────────────────────────────────────


@router.get("/market/requests", response_model=MarketRequestListOut)
def list_market_requests(
    company_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> MarketRequestListOut:
    """Open RFQs this supplier company may answer — trade terms only.

    Buyer contact details are never included: the platform stays the
    intermediary until a deal is open.
    """
    company = _company_or_404(db, account, company_id)
    rows = rfq_response_service.list_open_requests(db, company, limit=limit, offset=offset)

    mine = {
        r.request_id: r
        for r in db.query(RfqResponse)
        .filter(
            RfqResponse.company_id == company.id,
            RfqResponse.request_id.in_([r.id for r in rows] or [0]),
            RfqResponse.status != RfqResponseStatus.withdrawn,
        )
        .all()
    }
    return MarketRequestListOut(
        items=[
            MarketRequestOut(
                id=r.id,
                product=r.product_text,
                grade=r.grade_text,
                volume=r.volume if r.volume is not None else decimal.Decimal(0),
                volume_unit=r.volume_unit,
                incoterms=str(r.incoterms),
                destination_country=r.destination_country,
                port_or_city=r.port_or_city,
                desired_date=r.desired_date,
                validity_days=r.validity_days,
                urgency=str(r.urgency),
                required_docs=list(r.required_docs or []),
                created_at=r.created_at,
                my_response_id=mine[r.id].id if r.id in mine else None,
                my_response_status=str(mine[r.id].status) if r.id in mine else None,
            )
            for r in rows
        ]
    )
