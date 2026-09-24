"""Technologist marketplace — cabinet routes (/api/v1/portal/...).

Two sides, keyed differently, because one side is a person:

* **The expert** — `/portal/me/technologist/...`, keyed on the ACCOUNT. A
  company account calling these gets 403 `not_a_technologist`.
* **The factory** — `/portal/companies/{company_id}/tech-requests/...`, keyed on
  a company the caller is an active member of (404 otherwise, never 403 —
  `company_service.get_company_for`).
* **Threads** — `/portal/tech-threads/{thread_id}/...`, one address for both
  sides. `?company_id=` means "I am reading as that factory"; without it the
  caller reads as an expert. Either way the party check is server-side.

Literal paths precede parameterised ones throughout (FastAPI resolves
first-registered); `test_portal_technologists_api` pins that.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_not_verified
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.domains.technologists import profiles
from app.domains.technologists import requests as svc
from app.domains.technologists.models import (
    AUTHOR_COMPANY,
    AUTHOR_TECHNOLOGIST,
    TechMessage,
    TechnologistProfile,
    TechOffer,
    TechRequest,
    TechThread,
)
from app.domains.technologists.schemas import (
    CompanyOfferListOut,
    CompanyOfferOut,
    CompleteIn,
    ContactsOut,
    FeedCompanyOut,
    InviteIn,
    TechFeedItemOut,
    TechFeedListOut,
    TechMessageOut,
    TechMessagePageOut,
    TechnologistProfileIn,
    TechnologistProfileOwnOut,
    TechOfferIn,
    TechOfferOut,
    TechRequestIn,
    TechRequestListOut,
    TechRequestOut,
    TechReviewOut,
    TechThreadListOut,
    TechThreadOut,
)
from app.services import notification_service, storage_service

router = APIRouter(prefix="/portal", tags=["portal-technologists"])

_NOT_FOUND = "Not found"


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _409(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)


# ── Serializers ──────────────────────────────────────────────────────────────


def _own_out(profile: TechnologistProfile) -> TechnologistProfileOwnOut:
    return TechnologistProfileOwnOut(
        id=profile.id,
        full_name=profile.full_name,
        title=profile.title,
        country=profile.country,
        city=profile.city,
        photo_url="/api/v1/portal/me/technologist/photo" if profile.photo_key else None,
        years_experience=profile.years_experience,
        projects_count=profile.projects_count,
        countries_count=profile.countries_count,
        bio=profile.bio,
        industries=list(profile.industries or []),
        processes=list(profile.processes or []),
        materials=list(profile.materials or []),
        equipment_brands=list(profile.equipment_brands or []),
        work_formats=list(profile.work_formats or []),
        languages=list(profile.languages or []),
        contact_phone=profile.contact_phone,
        contact_email=profile.contact_email,
        status=profile.status,
        rejection_reason=profile.rejection_reason,
        submitted_at=profile.submitted_at,
        reviewed_at=profile.reviewed_at,
        is_listed=profiles.is_listed(profile),
        missing_fields=profiles.missing_fields(profile),
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
    )


def _offer_out(offer: TechOffer) -> TechOfferOut:
    return TechOfferOut.model_validate(offer, from_attributes=True)


def _request_out(db: Session, request: TechRequest) -> TechRequestOut:
    data = TechRequestOut.model_validate(request, from_attributes=True)
    data.offer_count = svc.offer_count(db, request.id)
    return data


def _factory_contacts(db: Session, request: TechRequest) -> ContactsOut:
    """Who at the factory posted it — the person the expert will call."""
    author = db.get(UserAccount, request.created_by_user_account_id)
    company = db.get(Company, request.company_id)
    return ContactsOut(
        name=(author.name if author else None) or svc.company_name(company),
        phone=author.phone if author else None,
    )


def _expert_contacts(profile: TechnologistProfile) -> ContactsOut:
    return ContactsOut(
        name=profile.full_name, phone=profile.contact_phone, email=profile.contact_email
    )


def _feed_item(db: Session, request: TechRequest, profile: TechnologistProfile) -> TechFeedItemOut:
    item = TechFeedItemOut.model_validate(request, from_attributes=True)
    thread = svc.thread_for(db, request.id, profile.id)
    if thread is not None:
        company = db.get(Company, request.company_id)
        item.company = FeedCompanyOut(id=request.company_id, name=svc.company_name(company))
        item.my_thread_id = thread.id
    item.invited = profile.id in svc.invited_profile_ids(db, request.id)
    mine = svc.my_offer(db, request.id, profile.id)
    item.my_offer = _offer_out(mine) if mine is not None else None
    if svc.contacts_visible(request, profile.id):
        item.contacts = _factory_contacts(db, request)
    return item


def _message_out(message: TechMessage, my_side: str) -> TechMessageOut:
    return TechMessageOut(
        id=message.id,
        author_kind=message.author_kind,
        mine=message.author_kind == my_side,
        body=message.body,
        has_file=bool(message.file_storage_path),
        file_name=message.file_name,
        created_at=message.created_at,
    )


def _thread_out(db: Session, thread: TechThread, request: TechRequest, my_side: str) -> TechThreadOut:
    if my_side == AUTHOR_TECHNOLOGIST:
        counterparty = svc.company_name(db.get(Company, request.company_id))
    else:
        profile = db.get(TechnologistProfile, thread.profile_id)
        counterparty = profile.full_name if profile else None
    return TechThreadOut(
        id=thread.id,
        request_id=request.id,
        request_number=request.number,
        profile_id=thread.profile_id,
        my_side=my_side,
        counterparty_name=counterparty,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


# ── Guards ───────────────────────────────────────────────────────────────────


def _expert(db: Session, account: UserAccount) -> TechnologistProfile:
    try:
        return profiles.get_or_create_own(db, account)
    except profiles.NotATechnologist as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not_a_technologist"
        ) from exc


def _company(db: Session, account: UserAccount, company_id: int) -> Company:
    try:
        return company_service.get_company_for(db, account, company_id)
    except company_service.CompanyNotFound as exc:
        raise _404(exc) from exc


def _company_request(
    db: Session, account: UserAccount, company_id: int, request_id: int
) -> TechRequest:
    try:
        return svc.get_for_company(db, account, company_id, request_id)
    except (company_service.CompanyNotFound, svc.TechRequestNotFound) as exc:
        raise _404(exc) from exc


def _company_offer(db: Session, request: TechRequest, offer_id: int) -> TechOffer:
    offer = db.get(TechOffer, offer_id)
    if offer is None or offer.request_id != request.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return offer


# ── The expert: profile ──────────────────────────────────────────────────────


@router.get("/me/technologist", response_model=TechnologistProfileOwnOut)
def get_own_profile(
    db: Session = Depends(get_db), account: UserAccount = Depends(get_current_account)
) -> TechnologistProfileOwnOut:
    """Created as an empty draft on first read, pre-filled from the application."""
    profile = _expert(db, account)
    db.commit()
    return _own_out(profile)


@router.put("/me/technologist", response_model=TechnologistProfileOwnOut)
def put_own_profile(
    body: TechnologistProfileIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechnologistProfileOwnOut:
    _expert(db, account)
    try:
        profile = profiles.update_own(db, account, body)
    except profiles.InvalidProfileTransition as exc:
        raise _409("profile_suspended") from exc
    db.commit()
    return _own_out(profile)


@router.post("/me/technologist/submit", response_model=TechnologistProfileOwnOut)
def submit_own_profile(
    db: Session = Depends(get_db), account: UserAccount = Depends(get_current_account)
) -> TechnologistProfileOwnOut:
    _expert(db, account)
    try:
        profile = profiles.submit_own(db, account)
    except profiles.ProfileIncomplete as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "profile_incomplete", "missing": exc.args[0]},
        ) from exc
    except profiles.InvalidProfileTransition as exc:
        raise _409("invalid_transition") from exc
    db.commit()
    return _own_out(profile)


@router.post("/me/technologist/photo", response_model=TechnologistProfileOwnOut)
async def upload_own_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechnologistProfileOwnOut:
    _expert(db, account)
    content = await file.read()
    try:
        profile = profiles.set_photo(db, account, content, file.filename or "photo")
    except profiles.InvalidProfileTransition as exc:
        raise _409("profile_suspended") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    return _own_out(profile)


@router.get("/me/technologist/photo", summary="The expert's CURRENT portrait (their own preview)")
def get_own_photo(
    db: Session = Depends(get_db), account: UserAccount = Depends(get_current_account)
) -> Response:
    profile = _expert(db, account)
    if not profile.photo_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    body = storage_service.get_object_bytes(profile.photo_key)
    media_type = "image/png" if profile.photo_key.endswith(".png") else "image/jpeg"
    return Response(content=body, media_type=media_type, headers={"Cache-Control": "no-store"})


# ── The expert: feed, offers, threads ────────────────────────────────────────


@router.get("/me/technologist/requests", response_model=TechFeedListOut)
def list_feed(
    invited: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechFeedListOut:
    """Open requests for a listed expert — empty (not 403) for one who is not
    listed yet: the page is theirs, it simply has nothing on it."""
    profile = _expert(db, account)
    rows = svc.feed_for(db, profile, invited_only=invited, limit=limit, offset=offset)
    db.commit()
    return TechFeedListOut(items=[_feed_item(db, r, profile) for r in rows])


@router.get("/me/technologist/threads", response_model=TechThreadListOut)
def list_expert_threads(
    db: Session = Depends(get_db), account: UserAccount = Depends(get_current_account)
) -> TechThreadListOut:
    profile = _expert(db, account)
    out = []
    for thread in svc.threads_for_expert(db, profile.id):
        request = db.get(TechRequest, thread.request_id)
        if request is not None:
            out.append(_thread_out(db, thread, request, AUTHOR_TECHNOLOGIST))
    db.commit()
    return TechThreadListOut(items=out)


def _expert_request(db: Session, profile: TechnologistProfile, request_id: int) -> TechRequest:
    try:
        return svc.get_for_expert(db, profile, request_id)
    except svc.TechRequestNotFound as exc:
        raise _404(exc) from exc


@router.get("/me/technologist/requests/{request_id}", response_model=TechFeedItemOut)
def get_feed_item(
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechFeedItemOut:
    profile = _expert(db, account)
    request = _expert_request(db, profile, request_id)
    db.commit()
    return _feed_item(db, request, profile)


@router.post(
    "/me/technologist/requests/{request_id}/offer",
    response_model=TechFeedItemOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_offer(
    request_id: int,
    body: TechOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechFeedItemOut:
    profile = _expert(db, account)
    request = _expert_request(db, profile, request_id)
    try:
        svc.submit_offer(db, request, profile, body)
    except svc.OfferConflict as exc:
        raise _409("offer_exists") from exc
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _feed_item(db, request, profile)


def _my_submitted_offer(db: Session, request: TechRequest, profile: TechnologistProfile) -> TechOffer:
    offer = svc.my_offer(db, request.id, profile.id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return offer


@router.put("/me/technologist/requests/{request_id}/offer", response_model=TechFeedItemOut)
def update_offer(
    request_id: int,
    body: TechOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechFeedItemOut:
    profile = _expert(db, account)
    request = _expert_request(db, profile, request_id)
    offer = _my_submitted_offer(db, request, profile)
    try:
        svc.update_offer(db, offer, profile, body)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _feed_item(db, request, profile)


@router.delete("/me/technologist/requests/{request_id}/offer", response_model=TechFeedItemOut)
def withdraw_offer(
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechFeedItemOut:
    profile = _expert(db, account)
    request = _expert_request(db, profile, request_id)
    offer = _my_submitted_offer(db, request, profile)
    try:
        svc.withdraw_offer(db, offer, profile)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _feed_item(db, request, profile)


@router.post("/me/technologist/requests/{request_id}/thread", response_model=TechThreadOut)
def open_expert_thread(
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechThreadOut:
    """«Задать вопрос» — idempotent; the same room each time."""
    profile = _expert(db, account)
    request = _expert_request(db, profile, request_id)
    try:
        thread = svc.open_thread(db, request, profile)
    except svc.TechRequestNotFound as exc:
        raise _404(exc) from exc
    db.commit()
    return _thread_out(db, thread, request, AUTHOR_TECHNOLOGIST)


# ── The factory ──────────────────────────────────────────────────────────────


@router.get("/companies/{company_id}/tech-requests", response_model=TechRequestListOut)
def list_company_requests(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestListOut:
    company = _company(db, account, company_id)
    return TechRequestListOut(
        items=[_request_out(db, r) for r in svc.list_for_company(db, company.id)]
    )


@router.post(
    "/companies/{company_id}/tech-requests",
    response_model=TechRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_company_request(
    company_id: int,
    body: TechRequestIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    company = _company(db, account, company_id)
    try:
        request = svc.create_request(db, company=company, account=account, data=body)
    except svc.CompanyNotVerified as exc:
        raise company_not_verified() from exc
    db.commit()
    db.refresh(request)
    return _request_out(db, request)


@router.get("/companies/{company_id}/tech-requests/{request_id}", response_model=TechRequestOut)
def get_company_request(
    company_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    return _request_out(db, _company_request(db, account, company_id, request_id))


@router.put("/companies/{company_id}/tech-requests/{request_id}", response_model=TechRequestOut)
def update_company_request(
    company_id: int,
    request_id: int,
    body: TechRequestIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    request = _company_request(db, account, company_id, request_id)
    try:
        svc.update_request(db, request, body)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _request_out(db, request)


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/cancel", response_model=TechRequestOut
)
def cancel_company_request(
    company_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    request = _company_request(db, account, company_id, request_id)
    try:
        svc.cancel_request(db, request, account)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _request_out(db, request)


@router.get(
    "/companies/{company_id}/tech-requests/{request_id}/offers", response_model=CompanyOfferListOut
)
def list_company_offers(
    company_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> CompanyOfferListOut:
    request = _company_request(db, account, company_id, request_id)
    items: list[CompanyOfferOut] = []
    for offer in svc.list_offers(db, request.id):
        profile = db.get(TechnologistProfile, offer.profile_id)
        if profile is None:
            continue
        thread = svc.thread_for(db, request.id, profile.id)
        items.append(
            CompanyOfferOut(
                **_offer_out(offer).model_dump(),
                technologist=profiles.public_card(profile),
                thread_id=thread.id if thread else None,
                contacts=(
                    _expert_contacts(profile)
                    if svc.contacts_visible(request, profile.id, offer=offer)
                    else None
                ),
            )
        )
    return CompanyOfferListOut(items=items)


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/offers/{offer_id}/accept",
    response_model=TechRequestOut,
)
def accept_offer(
    company_id: int,
    request_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    request = _company_request(db, account, company_id, request_id)
    offer = _company_offer(db, request, offer_id)
    try:
        svc.accept_offer(db, request, offer, account)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _request_out(db, request)


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/offers/{offer_id}/decline",
    response_model=TechRequestOut,
)
def decline_offer(
    company_id: int,
    request_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechRequestOut:
    request = _company_request(db, account, company_id, request_id)
    offer = _company_offer(db, request, offer_id)
    try:
        svc.decline_offer(db, request, offer, account)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return _request_out(db, request)


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/complete", response_model=TechReviewOut
)
def complete_request(
    company_id: int,
    request_id: int,
    body: CompleteIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechReviewOut:
    request = _company_request(db, account, company_id, request_id)
    try:
        review = svc.complete(db, request, account, rating=body.rating, text=body.text)
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return TechReviewOut.model_validate(review, from_attributes=True)


@router.get(
    "/companies/{company_id}/tech-requests/{request_id}/review",
    response_model=TechReviewOut | None,
)
def get_review(
    company_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechReviewOut | None:
    request = _company_request(db, account, company_id, request_id)
    review = svc.review_for(db, request.id)
    return TechReviewOut.model_validate(review, from_attributes=True) if review else None


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/invites",
    status_code=status.HTTP_204_NO_CONTENT,
)
def invite_expert(
    company_id: int,
    request_id: int,
    body: InviteIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    request = _company_request(db, account, company_id, request_id)
    try:
        svc.invite(db, request, body.profile_id, account)
    except profiles.ProfileNotFound as exc:
        raise _404(exc) from exc
    except svc.InvalidTechTransition as exc:
        raise _409(str(exc.args[0])) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/companies/{company_id}/tech-requests/{request_id}/threads/{profile_id}",
    response_model=TechThreadOut,
)
def open_company_thread(
    company_id: int,
    request_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechThreadOut:
    """«Написать» on an offer or an invitee. Idempotent."""
    request = _company_request(db, account, company_id, request_id)
    try:
        thread = svc.open_thread_as_company(db, request, profile_id)
    except svc.TechRequestNotFound as exc:
        raise _404(exc) from exc
    db.commit()
    return _thread_out(db, thread, request, AUTHOR_COMPANY)


# ── Threads (both sides) ─────────────────────────────────────────────────────


def _thread_as(
    db: Session, account: UserAccount, thread_id: int, company_id: int | None
) -> tuple[TechThread, TechRequest, str]:
    """Resolve the caller's side. `company_id` → the factory; none → the expert."""
    try:
        if company_id is not None:
            thread, request = svc.get_thread_for_company(db, account, company_id, thread_id)
            return thread, request, AUTHOR_COMPANY
        profile = profiles.find_own(db, account)
        if profile is None or account.applied_as != "technologist":
            raise svc.TechRequestNotFound(str(thread_id))
        thread, request = svc.get_thread_for_expert(db, profile, thread_id)
        return thread, request, AUTHOR_TECHNOLOGIST
    except (svc.TechRequestNotFound, company_service.CompanyNotFound) as exc:
        raise _404(exc) from exc


@router.get("/tech-threads/{thread_id}", response_model=TechThreadOut)
def get_thread(
    thread_id: int,
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechThreadOut:
    thread, request, side = _thread_as(db, account, thread_id, company_id)
    return _thread_out(db, thread, request, side)


@router.get("/tech-threads/{thread_id}/messages", response_model=TechMessagePageOut)
def list_thread_messages(
    thread_id: int,
    company_id: int | None = Query(default=None),
    after_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechMessagePageOut:
    thread, _request, side = _thread_as(db, account, thread_id, company_id)
    rows = svc.list_messages(db, thread, after_id=after_id, limit=limit)
    return TechMessagePageOut(
        items=[_message_out(m, side) for m in rows],
        last_id=rows[-1].id if rows else after_id,
    )


@router.post(
    "/tech-threads/{thread_id}/messages",
    response_model=TechMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_thread_message(
    thread_id: int,
    company_id: int | None = Form(default=None),
    body: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> TechMessageOut:
    thread, request, side = _thread_as(db, account, thread_id, company_id)
    content = await file.read() if file is not None else None
    try:
        message = svc.post_message(
            db,
            thread,
            author_kind=side,
            account=account,
            body=body,
            file_content=content,
            file_name=file.filename if file is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # The other side. A chat needs a cooldown, not just unread-dedup: once the
    # reader opens the bell, the very next line would ring it again.
    kind = notification_service.KIND_TECH_MESSAGE
    if side == AUTHOR_COMPANY:
        profile = db.get(TechnologistProfile, thread.profile_id)
        if profile is not None:
            title_key, body_key = notification_service.keys_for(kind)
            notification_service.notify_account(
                db,
                profile.user_account_id,
                kind=kind,
                title_key=title_key,
                body_key=body_key,
                params={"number": request.number, "thread_id": thread.id},
                entity="tech_feed",
                entity_id=str(request.id),
                cooldown_seconds=300,
            )
    else:
        title_key, body_key = notification_service.keys_for(kind)
        notification_service.notify_company(
            db,
            request.company_id,
            kind=kind,
            title_key=title_key,
            body_key=body_key,
            params={"number": request.number, "thread_id": thread.id},
            entity="tech_request",
            entity_id=str(request.id),
            cooldown_seconds=300,
        )

    db.commit()
    db.refresh(message)
    return _message_out(message, side)


@router.get("/tech-threads/{thread_id}/messages/{message_id}/file")
def get_thread_message_file(
    thread_id: int,
    message_id: int,
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, str]:
    """Presigned URL — participation re-checked, not assumed."""
    thread, _request, _side = _thread_as(db, account, thread_id, company_id)
    message = db.get(TechMessage, message_id)
    if message is None or message.thread_id != thread.id or not message.file_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return {"url": storage_service.presign_object(message.file_storage_path)}
