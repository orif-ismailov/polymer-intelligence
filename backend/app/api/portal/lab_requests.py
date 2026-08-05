"""Laboratory requests: the broadcast pool and its per-laboratory conversations.

A buyer states what needs testing once; every verified laboratory sees it; each
interested lab opens its OWN thread. Reading a lab's public profile is anonymous
(`/api/v1/public/directories/laboratories`); everything here needs a portal
session AND an active membership in the company doing the asking.

Prefix `/portal/lab`, NOT `/portal/laboratories`: `/portal/companies/{id}/lab-orders`
is the STAFF-run partner-lab flow (P6) and the two must not read as one family.

Route order matters: the literal `/requests…`, `/pool` and `/threads…` paths are
declared BEFORE anything parameterised, because FastAPI resolves
first-registered. `test_portal_lab_requests_api` pins the literal paths and their
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
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.laboratory import (
    LabRequest,
    LabRequestMessage,
    LabRequestThread,
)
from app.schemas.portal_laboratory import (
    LabMessageOut,
    LabMessagePageOut,
    LabPoolItemOut,
    LabPoolListOut,
    LabRequestCreateIn,
    LabRequestListOut,
    LabRequestOut,
    LabThreadListOut,
    LabThreadOpenIn,
    LabThreadOut,
)
from app.services import (
    company_service,
    laboratory_service,
    notification_service,
    storage_service,
)

router = APIRouter(prefix="/portal/lab", tags=["portal-lab-requests"])


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


def _request_out(db: Session, request: LabRequest) -> LabRequestOut:
    threads = laboratory_service.list_threads_for_request(db, request.id)
    return LabRequestOut(
        id=request.id,
        public_id=request.public_id,
        number=request.number,
        buyer_company_id=request.buyer_company_id,
        product_id=request.product_id,
        product_text=request.product_text,
        grade_text=request.grade_text,
        study_type=request.study_type,
        methods=list(request.methods or []),
        sample_qty=request.sample_qty,
        comment=request.comment,
        purpose=request.purpose,
        is_urgent=request.is_urgent,
        desired_date=request.desired_date,
        contact_name=request.contact_name,
        contact_email=request.contact_email,
        contact_phone=request.contact_phone,
        status=str(request.status),
        created_at=request.created_at,
        buyer_name=_company_name(db, request.buyer_company_id),
        thread_count=len(threads),
    )


def _pool_item_out(
    db: Session, request: LabRequest, my_thread_id: int | None
) -> LabPoolItemOut:
    return LabPoolItemOut(
        id=request.id,
        number=request.number,
        buyer_company_id=request.buyer_company_id,
        buyer_name=_company_name(db, request.buyer_company_id),
        product_text=request.product_text,
        grade_text=request.grade_text,
        study_type=request.study_type,
        methods=list(request.methods or []),
        sample_qty=request.sample_qty,
        comment=request.comment,
        purpose=request.purpose,
        is_urgent=request.is_urgent,
        desired_date=request.desired_date,
        status=str(request.status),
        created_at=request.created_at,
        my_thread_id=my_thread_id,
    )


def _thread_out(
    db: Session,
    thread: LabRequestThread,
    request: LabRequest,
    viewer_company_id: int,
) -> LabThreadOut:
    role = laboratory_service.thread_party_role(thread, request, viewer_company_id)
    other_id = (
        request.buyer_company_id if role == "laboratory" else thread.laboratory_company_id
    )
    return LabThreadOut(
        id=thread.id,
        lab_request_id=request.id,
        request_number=request.number,
        laboratory_company_id=thread.laboratory_company_id,
        counterparty_name=_company_name(db, other_id),
        my_role=role or "",
        product_text=request.product_text,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _message_out(message: LabRequestMessage) -> LabMessageOut:
    return LabMessageOut(
        id=message.id,
        author_company_id=message.author_company_id,
        body=message.body,
        has_file=bool(message.file_storage_path),
        file_name=message.file_name,
        created_at=message.created_at,
    )


# ── Requests ──────────────────────────────────────────────────────────────────


@router.get(
    "/requests", response_model=LabRequestListOut, summary="A buyer's own requests"
)
def list_requests(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabRequestListOut:
    """GET /portal/lab/requests — what this company has filed.

    The laboratory side is `/pool`, which is a different question with a different
    predicate — not a `side=` flag on this one.
    """
    company = _company_or_404(db, account, company_id)
    rows = laboratory_service.list_lab_requests_for(db, company.id)
    return LabRequestListOut(items=[_request_out(db, r) for r in rows])


@router.get(
    "/pool", response_model=LabPoolListOut, summary="Open requests for laboratories"
)
def list_pool(
    company_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabPoolListOut:
    """GET /portal/lab/pool — every open request, for a verified laboratory.

    Empty rather than 403 for a non-laboratory: whether a company holds a confirmed
    laboratory role is not a secret, but "here is a list you may not read" is a
    worse answer than an empty one for a page that simply is not theirs.
    """
    company = _company_or_404(db, account, company_id)
    rows = laboratory_service.list_open_requests_for_lab(
        db, company, limit=limit, offset=offset
    )
    mine = {
        t.lab_request_id: t.id
        for t in laboratory_service.list_threads_for_company(db, company.id)
        if t.laboratory_company_id == company.id
    }
    return LabPoolListOut(
        items=[_pool_item_out(db, r, mine.get(r.id)) for r in rows]
    )


@router.post(
    "/requests",
    response_model=LabRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="File a laboratory request (broadcast)",
)
def create_request(
    body: LabRequestCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabRequestOut:
    """POST /portal/lab/requests — «Отправить заявку»."""
    buyer = _company_or_404(db, account, body.company_id)
    request = laboratory_service.create_lab_request(
        db,
        buyer=buyer,
        account=account,
        product_id=body.product_id,
        product_text=body.product_text,
        grade_text=body.grade_text,
        study_type=body.study_type,
        methods=body.methods,
        sample_qty=body.sample_qty,
        comment=body.comment,
        purpose=body.purpose,
        is_urgent=body.is_urgent,
        desired_date=body.desired_date,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )

    # Fan out to every laboratory, in the same transaction as the insert: a
    # broadcast nobody is told about is a broadcast nobody answers.
    #
    # One `notify_company` per laboratory. That is fine while the directory is in
    # the tens; past a few hundred this belongs on the `notify` queue as a task,
    # the way `app/tasks/rfq_push.py` handles the polymer-RFQ fan-out.
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LAB_REQUEST_NEW
    )
    for lab in laboratory_service.list_lab_companies(db):
        if lab.id == buyer.id:
            continue
        notification_service.notify_company(
            db,
            lab.id,
            kind=notification_service.KIND_LAB_REQUEST_NEW,
            title_key=title_key,
            body_key=body_key,
            params={
                "request_id": request.id,
                "number": request.number,
                "product": request.product_text,
                "buyer": buyer.short_name or buyer.legal_name or "",
            },
            entity="lab_request",
            entity_id=str(request.id),
            exclude_account_id=account.id,
        )

    db.commit()
    db.refresh(request)
    return _request_out(db, request)


@router.get(
    "/requests/{request_id}",
    response_model=LabRequestOut,
    summary="One laboratory request",
)
def get_request(
    request_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabRequestOut:
    """GET /portal/lab/requests/{id} — the buyer, or any verified laboratory."""
    try:
        request = laboratory_service.get_lab_request_for(
            db, account, request_id, company_id
        )
    except laboratory_service.NotLabParticipant as exc:
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
    "/threads", response_model=LabThreadListOut, summary="This company's threads"
)
def list_threads(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabThreadListOut:
    """GET /portal/lab/threads — both sides: carried, and on own requests."""
    company = _company_or_404(db, account, company_id)
    out: list[LabThreadOut] = []
    for thread in laboratory_service.list_threads_for_company(db, company.id):
        request = db.get(LabRequest, thread.lab_request_id)
        if request is not None:
            out.append(_thread_out(db, thread, request, company.id))
    return LabThreadListOut(items=out)


@router.get(
    "/threads/{thread_id}/messages",
    response_model=LabMessagePageOut,
    summary="Poll a thread",
)
def list_messages(
    thread_id: int,
    company_id: int = Query(...),
    after_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabMessagePageOut:
    """GET /portal/lab/threads/{id}/messages — delta poll via `after_id`."""
    try:
        thread, _request = laboratory_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except laboratory_service.NotLabParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    rows = laboratory_service.list_messages(db, thread, after_id=after_id, limit=limit)
    return LabMessagePageOut(
        items=[_message_out(m) for m in rows],
        last_id=rows[-1].id if rows else after_id,
    )


@router.post(
    "/threads/{thread_id}/messages",
    response_model=LabMessageOut,
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
) -> LabMessageOut:
    """POST /portal/lab/threads/{id}/messages — text and/or one file."""
    try:
        thread, request = laboratory_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except laboratory_service.NotLabParticipant as exc:
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
        message = laboratory_service.post_message(
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
    role = laboratory_service.thread_party_role(thread, request, company.id)
    target = (
        request.buyer_company_id if role == "laboratory" else thread.laboratory_company_id
    )
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LAB_MESSAGE
    )
    notification_service.notify_company(
        db,
        target,
        kind=notification_service.KIND_LAB_MESSAGE,
        title_key=title_key,
        body_key=body_key,
        params={"thread_id": thread.id, "number": request.number},
        entity="lab_thread",
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
        thread, _request = laboratory_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except laboratory_service.NotLabParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc

    message = db.get(LabRequestMessage, message_id)
    if message is None or message.thread_id != thread.id or not message.file_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"url": storage_service.presign_object(message.file_storage_path)}


@router.post(
    "/requests/{request_id}/threads",
    response_model=LabThreadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open (or reopen) a laboratory's conversation on a request",
)
def open_thread(
    request_id: int,
    body: LabThreadOpenIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> LabThreadOut:
    """POST /portal/lab/requests/{id}/threads — «Ответить».

    Idempotent: the client calls it every time the chat screen mounts, and the
    laboratory must land in the same room each time.
    """
    laboratory = _company_or_404(db, account, body.company_id)
    request = db.get(LabRequest, request_id)
    if request is None or not laboratory_service.is_visible_to(db, request, laboratory):
        # Covers "no such request", "not a laboratory" and "your own request" with
        # one answer — none of which the caller should be able to tell apart.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    thread = laboratory_service.open_or_get_thread(
        db, request=request, laboratory=laboratory, account=account
    )
    db.commit()
    db.refresh(thread)
    return _thread_out(db, thread, request, laboratory.id)
