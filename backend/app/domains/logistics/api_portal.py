"""Logistics requests: the broadcast pool and its per-carrier conversations.

A buyer states a job once; every verified logistics company sees it; each
interested carrier opens its OWN thread. Reading a carrier's public profile is
anonymous (`/api/v1/public/directories/logistics`); everything here needs a
portal session AND an active membership in the company doing the asking.

Route order matters: the literal `/requests…`, `/pool` and `/threads…` paths are
declared BEFORE anything parameterised, because FastAPI resolves
first-registered. `test_portal_logistics_api` pins the literal paths and their
order so a reorder fails there rather than in production.
"""

from __future__ import annotations

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
from app.api.portal.deps import require_business_role
from app.core.db import get_db
from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.domains.logistics import service as logistics_service
from app.domains.logistics.models import (
    LogisticsRequest,
    LogisticsRequestMessage,
    LogisticsRequestThread,
)
from app.domains.logistics.schemas import (
    LogisticsMessageOut,
    LogisticsMessagePageOut,
    LogisticsPoolItemOut,
    LogisticsPoolListOut,
    LogisticsRequestCreateIn,
    LogisticsRequestListOut,
    LogisticsRequestOut,
    LogisticsThreadListOut,
    LogisticsThreadOpenIn,
    LogisticsThreadOut,
)
from app.models.accounts import UserAccount
from app.services import (
    notification_service,
    storage_service,
)

router = APIRouter(prefix="/portal/logistics", tags=["portal-logistics"])


def _company_or_404(db: Session, account: UserAccount, company_id: int) -> Company:
    try:
        return company_service.get_company_for(db, account, company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc


def _company_name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    return (company.short_name or company.legal_name) if company else None


def _request_out(db: Session, request: LogisticsRequest) -> LogisticsRequestOut:
    threads = logistics_service.list_threads_for_request(db, request.id)
    return LogisticsRequestOut(
        id=request.id,
        public_id=request.public_id,
        number=request.number,
        buyer_company_id=request.buyer_company_id,
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
        buyer_name=_company_name(db, request.buyer_company_id),
        thread_count=len(threads),
    )


def _pool_item_out(
    db: Session, request: LogisticsRequest, my_thread_id: int | None
) -> LogisticsPoolItemOut:
    return LogisticsPoolItemOut(
        id=request.id,
        number=request.number,
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
        status=str(request.status),
        created_at=request.created_at,
        my_thread_id=my_thread_id,
    )


def _thread_out(
    db: Session,
    thread: LogisticsRequestThread,
    request: LogisticsRequest,
    viewer_company_id: int,
) -> LogisticsThreadOut:
    role = logistics_service.thread_party_role(thread, request, viewer_company_id)
    other_id = (
        request.buyer_company_id if role == "carrier" else thread.carrier_company_id
    )
    return LogisticsThreadOut(
        id=thread.id,
        logistics_request_id=request.id,
        request_number=request.number,
        carrier_company_id=thread.carrier_company_id,
        counterparty_name=_company_name(db, other_id),
        my_role=role or "",
        cargo_name=request.cargo_name,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _message_out(message: LogisticsRequestMessage) -> LogisticsMessageOut:
    return LogisticsMessageOut(
        id=message.id,
        author_company_id=message.author_company_id,
        body=message.body,
        has_file=bool(message.file_storage_path),
        file_name=message.file_name,
        created_at=message.created_at,
    )


# ── Requests ──────────────────────────────────────────────────────────────────


@router.get(
    "/requests", response_model=LogisticsRequestListOut, summary="A buyer's own requests"
)
def list_requests(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsRequestListOut:
    """GET /portal/logistics/requests — what this company has filed.

    The carrier side is `/pool`, which is a different question with a different
    predicate — not a `side=` flag on this one.
    """
    company = _company_or_404(db, account, company_id)
    rows = logistics_service.list_logistics_requests_for(db, company.id)
    return LogisticsRequestListOut(items=[_request_out(db, r) for r in rows])


@router.get(
    "/pool", response_model=LogisticsPoolListOut, summary="Open requests for carriers"
)
def list_pool(
    company_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsPoolListOut:
    """GET /portal/logistics/pool — every open request, for a verified carrier.

    Empty rather than 403 for a non-carrier: whether a company holds a confirmed
    logistics role is not a secret, but "here is a list you may not read" is a
    worse answer than an empty one for a page that simply is not theirs.
    """
    company = _company_or_404(db, account, company_id)
    rows = logistics_service.list_open_requests_for_carrier(
        db, company, limit=limit, offset=offset
    )
    mine = {
        t.logistics_request_id: t.id
        for t in logistics_service.list_threads_for_company(db, company.id)
        if t.carrier_company_id == company.id
    }
    return LogisticsPoolListOut(
        items=[_pool_item_out(db, r, mine.get(r.id)) for r in rows]
    )


@router.post(
    "/requests",
    response_model=LogisticsRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="File a logistics request (broadcast)",
)
def create_request(
    body: LogisticsRequestCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsRequestOut:
    """POST /portal/logistics/requests — «Отправить заявку»."""
    buyer = _company_or_404(db, account, body.company_id)
    require_business_role(buyer, company_service.LOGISTICS_ORDERING_ROLES)
    request = logistics_service.create_logistics_request(
        db,
        buyer=buyer,
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

    # Fan out to every carrier, in the same transaction as the insert: a
    # broadcast nobody is told about is a broadcast nobody answers.
    #
    # One `notify_company` per carrier. That is fine while the directory is in
    # the tens; past a few hundred this belongs on the `notify` queue as a task,
    # the way `app/tasks/rfq_push.py` handles the polymer-RFQ fan-out.
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LOGISTICS_REQUEST_NEW
    )
    for carrier in logistics_service.list_carrier_companies(db):
        if carrier.id == buyer.id:
            continue
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
    """GET /portal/logistics/requests/{id} — the buyer, or any verified carrier."""
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


# ── Conversations ─────────────────────────────────────────────────────────────


@router.get(
    "/threads", response_model=LogisticsThreadListOut, summary="This company's threads"
)
def list_threads(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsThreadListOut:
    """GET /portal/logistics/threads — both sides: carried, and on own requests."""
    company = _company_or_404(db, account, company_id)
    out: list[LogisticsThreadOut] = []
    for thread in logistics_service.list_threads_for_company(db, company.id):
        request = db.get(LogisticsRequest, thread.logistics_request_id)
        if request is not None:
            out.append(_thread_out(db, thread, request, company.id))
    return LogisticsThreadListOut(items=out)


@router.get(
    "/threads/{thread_id}/messages",
    response_model=LogisticsMessagePageOut,
    summary="Poll a thread",
)
def list_messages(
    thread_id: int,
    company_id: int = Query(...),
    after_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsMessagePageOut:
    """GET /portal/logistics/threads/{id}/messages — delta poll via `after_id`."""
    try:
        thread, _request = logistics_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except logistics_service.NotLogisticsParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    rows = logistics_service.list_messages(db, thread, after_id=after_id, limit=limit)
    return LogisticsMessagePageOut(
        items=[_message_out(m) for m in rows],
        last_id=rows[-1].id if rows else after_id,
    )


@router.post(
    "/threads/{thread_id}/messages",
    response_model=LogisticsMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Post to a thread",
)
async def post_message(
    thread_id: int,
    company_id: int = Form(...),
    body: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsMessageOut:
    """POST /portal/logistics/threads/{id}/messages — text and/or one file."""
    try:
        thread, request = logistics_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except logistics_service.NotLogisticsParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    company = _company_or_404(db, account, company_id)
    content = await file.read() if file is not None else None
    try:
        message = logistics_service.post_message(
            db,
            thread,
            account,
            company,
            body,
            file_content=content,
            file_name=file.filename if file is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # The other side, whichever that is.
    role = logistics_service.thread_party_role(thread, request, company.id)
    target = (
        request.buyer_company_id if role == "carrier" else thread.carrier_company_id
    )
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LOGISTICS_MESSAGE
    )
    notification_service.notify_company(
        db,
        target,
        kind=notification_service.KIND_LOGISTICS_MESSAGE,
        title_key=title_key,
        body_key=body_key,
        params={"thread_id": thread.id, "number": request.number},
        entity="logistics_thread",
        entity_id=str(thread.id),
        exclude_account_id=account.id,
        # A chat needs a cooldown, not just unread-dedup: the moment the reader
        # opens the bell the next line typed would ring it again.
        cooldown_seconds=300,
    )

    db.commit()
    db.refresh(message)
    return _message_out(message)


@router.get(
    "/threads/{thread_id}/messages/{message_id}/file",
    summary="Presigned URL for a chat attachment",
)
def get_message_file(
    thread_id: int,
    message_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, str]:
    """GET …/messages/{id}/file — participation is re-checked, not assumed."""
    try:
        thread, _request = logistics_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except logistics_service.NotLogisticsParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    message = db.get(LogisticsRequestMessage, message_id)
    if message is None or message.thread_id != thread.id or not message.file_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"url": storage_service.presign_object(message.file_storage_path)}


@router.post(
    "/requests/{request_id}/threads",
    response_model=LogisticsThreadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open (or reopen) a carrier's conversation on a request",
)
def open_thread(
    request_id: int,
    body: LogisticsThreadOpenIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LogisticsThreadOut:
    """POST /portal/logistics/requests/{id}/threads — «Ответить».

    Idempotent: the client calls it every time the chat screen mounts, and the
    carrier must land in the same room each time.
    """
    carrier = _company_or_404(db, account, body.company_id)
    request = db.get(LogisticsRequest, request_id)
    if request is None or not logistics_service.is_visible_to(db, request, carrier):
        # Covers "no such request", "not a carrier" and "your own request" with
        # one answer — none of which the caller should be able to tell apart.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    thread = logistics_service.open_or_get_thread(
        db, request=request, carrier=carrier, account=account
    )
    db.commit()
    db.refresh(thread)
    return _thread_out(db, thread, request, carrier.id)
