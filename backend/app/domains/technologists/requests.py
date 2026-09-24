"""Technologist requests: the broadcast, offers, threads, completion.

Lifecycle of a request::

    open ──accept_offer──▶ assigned ──complete(review)──▶ completed
      │                        │
      └───────cancel───────────┴──▶ cancelled

and of an offer: `submitted → accepted | declined | withdrawn`, one ACTIVE
(submitted/accepted) per (request, expert) — enforced by a partial unique index
as well as here.

**Who sees what.**

* The feed is every `open` request, for every LISTED expert. `feed_for` and
  `_expert_can_read` must agree, or an expert sees a card the detail route 404s.
* The factory is anonymous to an expert until a thread exists between them
  (`company_visible_to`): the job is public, who is asking is not.
* Contacts cross only after acceptance, and only between the two parties to the
  accepted offer (`contacts_visible`). The platform brokers the introduction;
  contract and payment happen off it.

Every function flushes and leaves the commit to the caller.
"""

from __future__ import annotations

import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core import numbering
from app.core.time import utcnow
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.domains.technologists import profiles
from app.domains.technologists.models import (
    AUTHOR_COMPANY,
    AUTHOR_TECHNOLOGIST,
    OFFER_ACCEPTED,
    OFFER_DECLINED,
    OFFER_SUBMITTED,
    OFFER_WITHDRAWN,
    REQUEST_ASSIGNED,
    REQUEST_CANCELLED,
    REQUEST_COMPLETED,
    REQUEST_OPEN,
    TechMessage,
    TechnologistProfile,
    TechOffer,
    TechRequest,
    TechRequestInvite,
    TechReview,
    TechThread,
)
from app.domains.technologists.schemas import TechOfferIn, TechRequestIn
from app.models.enums import CompanyStatus
from app.services import notification_service, storage_service
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)

MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024

_ACTIVE_OFFER = (OFFER_SUBMITTED, OFFER_ACCEPTED)


class TechRequestNotFound(Exception):
    """No such request/offer/thread FOR THIS CALLER — one answer for "missing"
    and "not yours", so existence is never confirmed to an outsider."""


class InvalidTechTransition(Exception):
    """The move is not allowed from the current state. `args[0]` is a code."""


class CompanyNotVerified(Exception):
    """Only a verified company may post — mapped to `portal.deps.company_not_verified`."""


class OfferConflict(Exception):
    """The expert already has an active offer on this request."""


# ── Numbering + small helpers ────────────────────────────────────────────────


def generate_number(db: Session) -> str:
    value = numbering.next_in_sequence(
        db, "tech_request_seq", numbering.LOCK_BASE_TECH_REQUEST
    )
    return f"IMX-TECH-{value:06d}"


def company_name(company: Company | None) -> str | None:
    if company is None:
        return None
    return company.short_name or company.legal_name


def _audit(db: Session, action: str, entity_id: int, details: dict[str, object]) -> None:
    write_audit(db, None, action, "tech_requests", str(entity_id), details)


def _notify_experts(
    db: Session, account_ids: list[int], kind: str, params: dict[str, object], request_id: int
) -> None:
    title_key, body_key = notification_service.keys_for(kind)
    for account_id in account_ids:
        notification_service.notify_account(
            db,
            account_id,
            kind=kind,
            title_key=title_key,
            body_key=body_key,
            params=params,
            # The EXPERT's address for a request — `tech_request` is the
            # factory's. `notificationLink` sees only (entity, id), and one id
            # has two readers with two pages.
            entity="tech_feed",
            entity_id=str(request_id),
        )


def _notify_company(
    db: Session,
    request: TechRequest,
    kind: str,
    params: dict[str, object],
    *,
    cooldown_seconds: int | None = None,
    exclude_account_id: int | None = None,
) -> None:
    title_key, body_key = notification_service.keys_for(kind)
    notification_service.notify_company(
        db,
        request.company_id,
        kind=kind,
        title_key=title_key,
        body_key=body_key,
        params={"number": request.number, **params},
        entity="tech_request",
        entity_id=str(request.id),
        exclude_account_id=exclude_account_id,
        cooldown_seconds=cooldown_seconds,
    )


# ── Requests (the factory side) ──────────────────────────────────────────────


def create_request(
    db: Session,
    *,
    company: Company,
    account: UserAccount,
    data: TechRequestIn,
    source: str = "form",
) -> TechRequest:
    """Post a request and tell every listed expert whose processes include it.

    Verified companies only, as with an RFQ: an expert travels to a factory on
    the strength of this row, so who is asking has to be known.
    """
    if company.status != CompanyStatus.verified:
        raise CompanyNotVerified(str(company.id))

    request = TechRequest(
        number=generate_number(db),
        company_id=company.id,
        created_by_user_account_id=account.id,
        source=source,
        status=REQUEST_OPEN,
        **data.model_dump(),
    )
    db.add(request)
    db.flush()
    _audit(db, "tech_request.create", request.id, {"company_id": company.id, "source": source})

    matching = db.execute(
        sa.select(TechnologistProfile.user_account_id).where(
            TechnologistProfile.published_snapshot.is_not(None),
            TechnologistProfile.status != "suspended",
            TechnologistProfile.published_snapshot["processes"].contains([request.process]),
        )
    ).scalars()
    _notify_experts(
        db,
        list(matching),
        notification_service.KIND_TECH_REQUEST_NEW,
        {"number": request.number, "process": request.process},
        request.id,
    )
    return request


def get_for_company(db: Session, account: UserAccount, company_id: int, request_id: int) -> TechRequest:
    """A request of the caller's own company. `CompanyNotFound` for a non-member."""
    company = company_service.get_company_for(db, account, company_id)
    request = db.get(TechRequest, request_id)
    if request is None or request.company_id != company.id:
        raise TechRequestNotFound(str(request_id))
    return request


def list_for_company(db: Session, company_id: int) -> list[TechRequest]:
    return list(
        db.execute(
            sa.select(TechRequest)
            .where(TechRequest.company_id == company_id)
            .order_by(TechRequest.id.desc())
        ).scalars()
    )


def offer_count(db: Session, request_id: int) -> int:
    return int(
        db.execute(
            sa.select(sa.func.count())
            .select_from(TechOffer)
            .where(TechOffer.request_id == request_id, TechOffer.status.in_(_ACTIVE_OFFER))
        ).scalar_one()
    )


def update_request(db: Session, request: TechRequest, data: TechRequestIn) -> TechRequest:
    """Only while nobody has answered: an expert priced what they read."""
    if request.status != REQUEST_OPEN:
        raise InvalidTechTransition("not_open")
    if offer_count(db, request.id):
        raise InvalidTechTransition("has_offers")
    for field, value in data.model_dump().items():
        setattr(request, field, value)
    db.flush()
    return request


def cancel_request(db: Session, request: TechRequest, account: UserAccount) -> None:
    if request.status not in (REQUEST_OPEN, REQUEST_ASSIGNED):
        raise InvalidTechTransition("not_cancellable")
    request.status = REQUEST_CANCELLED
    request.cancelled_at = utcnow()
    for offer in _offers(db, request.id, statuses=_ACTIVE_OFFER):
        offer.status = OFFER_DECLINED
    _audit(db, "tech_request.cancel", request.id, {"account_id": account.id})
    db.flush()


def invite(db: Session, request: TechRequest, profile_id: int, account: UserAccount) -> TechRequestInvite:
    """Point an open request at one listed expert. Idempotent."""
    if request.status != REQUEST_OPEN:
        raise InvalidTechTransition("not_open")
    profile = profiles.get_listed(db, profile_id)
    existing = db.execute(
        sa.select(TechRequestInvite).where(
            TechRequestInvite.request_id == request.id,
            TechRequestInvite.profile_id == profile.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = TechRequestInvite(
        request_id=request.id, profile_id=profile.id, created_by_user_account_id=account.id
    )
    db.add(row)
    db.flush()
    _notify_experts(
        db,
        [profile.user_account_id],
        notification_service.KIND_TECH_INVITE,
        {"number": request.number},
        request.id,
    )
    return row


def invited_profile_ids(db: Session, request_id: int) -> set[int]:
    return set(
        db.execute(
            sa.select(TechRequestInvite.profile_id).where(TechRequestInvite.request_id == request_id)
        ).scalars()
    )


# ── The expert side ──────────────────────────────────────────────────────────


def feed_for(
    db: Session,
    profile: TechnologistProfile,
    *,
    invited_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[TechRequest]:
    """Open requests, newest first. Empty for an unlisted expert."""
    if not profiles.is_listed(profile):
        return []
    stmt = sa.select(TechRequest).where(TechRequest.status == REQUEST_OPEN)
    if invited_only:
        stmt = stmt.where(
            TechRequest.id.in_(
                sa.select(TechRequestInvite.request_id).where(
                    TechRequestInvite.profile_id == profile.id
                )
            )
        )
    stmt = stmt.order_by(TechRequest.created_at.desc(), TechRequest.id.desc())
    return list(db.execute(stmt.limit(max(1, min(limit, 200))).offset(max(0, offset))).scalars())


def _expert_can_read(db: Session, request: TechRequest, profile: TechnologistProfile) -> bool:
    """Open to any listed expert; after that only to one who took part."""
    if request.status == REQUEST_OPEN:
        return profiles.is_listed(profile)
    return thread_for(db, request.id, profile.id) is not None or (
        my_offer(db, request.id, profile.id) is not None
    )


def get_for_expert(db: Session, profile: TechnologistProfile, request_id: int) -> TechRequest:
    request = db.get(TechRequest, request_id)
    if request is None or not _expert_can_read(db, request, profile):
        raise TechRequestNotFound(str(request_id))
    return request


def company_visible_to(db: Session, request: TechRequest, profile: TechnologistProfile) -> bool:
    """The factory's name crosses once the two sides are talking."""
    return thread_for(db, request.id, profile.id) is not None


def contacts_visible(request: TechRequest, profile_id: int, *, offer: TechOffer | None = None) -> bool:
    """Both sides' contacts, only between the parties to the ACCEPTED offer.

    `offer` saves a query when the caller already holds the accepted row; with
    none, the check falls back to comparing the assigned offer id lazily loaded.
    """
    if request.status not in (REQUEST_ASSIGNED, REQUEST_COMPLETED):
        return False
    if request.assigned_offer_id is None:
        return False
    if offer is not None:
        return offer.id == request.assigned_offer_id and offer.profile_id == profile_id
    from sqlalchemy.orm import object_session  # noqa: PLC0415

    session = object_session(request)
    accepted = session.get(TechOffer, request.assigned_offer_id) if session else None
    return accepted is not None and accepted.profile_id == profile_id


def _offers(db: Session, request_id: int, *, statuses: tuple[str, ...] | None = None) -> list[TechOffer]:
    stmt = sa.select(TechOffer).where(TechOffer.request_id == request_id)
    if statuses:
        stmt = stmt.where(TechOffer.status.in_(statuses))
    return list(db.execute(stmt.order_by(TechOffer.id)).scalars())


def list_offers(db: Session, request_id: int) -> list[TechOffer]:
    """What the factory sees: every offer ever made, withdrawn ones excluded."""
    return [o for o in _offers(db, request_id) if o.status != OFFER_WITHDRAWN]


def my_offer(db: Session, request_id: int, profile_id: int) -> TechOffer | None:
    """The expert's latest offer on a request, whatever its status."""
    return db.execute(
        sa.select(TechOffer)
        .where(TechOffer.request_id == request_id, TechOffer.profile_id == profile_id)
        .order_by(TechOffer.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def submit_offer(
    db: Session, request: TechRequest, profile: TechnologistProfile, data: TechOfferIn
) -> TechOffer:
    """Offer on an open request. Opens the thread — an offer is the start of the
    conversation, and the factory's reply has to have somewhere to go."""
    if request.status != REQUEST_OPEN or not profiles.is_listed(profile):
        raise InvalidTechTransition("not_open")
    active = db.execute(
        sa.select(TechOffer.id).where(
            TechOffer.request_id == request.id,
            TechOffer.profile_id == profile.id,
            TechOffer.status.in_(_ACTIVE_OFFER),
        )
    ).first()
    if active is not None:
        raise OfferConflict(str(request.id))

    offer = TechOffer(
        request_id=request.id, profile_id=profile.id, status=OFFER_SUBMITTED, **data.model_dump()
    )
    db.add(offer)
    db.flush()
    open_thread(db, request, profile)
    _audit(db, "tech_offer.submit", request.id, {"offer_id": offer.id, "profile_id": profile.id})
    _notify_company(
        db,
        request,
        notification_service.KIND_TECH_OFFER_NEW,
        {"expert": (profile.published_snapshot or {}).get("full_name") or ""},
    )
    return offer


def _own_submitted(offer: TechOffer, profile: TechnologistProfile) -> None:
    if offer.profile_id != profile.id:
        raise TechRequestNotFound(str(offer.id))
    if offer.status != OFFER_SUBMITTED:
        raise InvalidTechTransition("not_submitted")


def update_offer(db: Session, offer: TechOffer, profile: TechnologistProfile, data: TechOfferIn) -> TechOffer:
    _own_submitted(offer, profile)
    for field, value in data.model_dump().items():
        setattr(offer, field, value)
    db.flush()
    return offer


def withdraw_offer(db: Session, offer: TechOffer, profile: TechnologistProfile) -> None:
    _own_submitted(offer, profile)
    offer.status = OFFER_WITHDRAWN
    _audit(db, "tech_offer.withdraw", offer.request_id, {"offer_id": offer.id})
    db.flush()


def _offer_on(request: TechRequest, offer: TechOffer) -> None:
    if offer.request_id != request.id:
        raise TechRequestNotFound(str(offer.id))


def accept_offer(db: Session, request: TechRequest, offer: TechOffer, account: UserAccount) -> None:
    """Assign the request. Every other live offer is declined in the same flush,
    and each expert is told which way it went."""
    _offer_on(request, offer)
    if request.status != REQUEST_OPEN:
        raise InvalidTechTransition("not_open")
    if offer.status != OFFER_SUBMITTED:
        raise InvalidTechTransition("not_submitted")

    offer.status = OFFER_ACCEPTED
    request.status = REQUEST_ASSIGNED
    request.assigned_offer_id = offer.id
    losers = [o for o in _offers(db, request.id, statuses=(OFFER_SUBMITTED,)) if o.id != offer.id]
    for other in losers:
        other.status = OFFER_DECLINED
    db.flush()
    _audit(db, "tech_offer.accept", request.id, {"offer_id": offer.id, "account_id": account.id})

    for decided, outcome in [(offer, "accepted"), *[(o, "declined") for o in losers]]:
        profile = db.get(TechnologistProfile, decided.profile_id)
        if profile is not None:
            _notify_experts(
                db,
                [profile.user_account_id],
                notification_service.KIND_TECH_OFFER_DECIDED,
                {"number": request.number, "outcome": outcome},
                request.id,
            )


def decline_offer(db: Session, request: TechRequest, offer: TechOffer, account: UserAccount) -> None:
    _offer_on(request, offer)
    if request.status != REQUEST_OPEN or offer.status != OFFER_SUBMITTED:
        raise InvalidTechTransition("not_submitted")
    offer.status = OFFER_DECLINED
    db.flush()
    _audit(db, "tech_offer.decline", request.id, {"offer_id": offer.id, "account_id": account.id})
    profile = db.get(TechnologistProfile, offer.profile_id)
    if profile is not None:
        _notify_experts(
            db,
            [profile.user_account_id],
            notification_service.KIND_TECH_OFFER_DECIDED,
            {"number": request.number, "outcome": "declined"},
            request.id,
        )


def complete(
    db: Session, request: TechRequest, account: UserAccount, *, rating: int, text: str | None
) -> TechReview:
    """Close an assigned request with the factory's review, and refresh the
    expert's rating from every review they have — recomputed, not incremented,
    so the stored average can never drift from its rows."""
    if request.status != REQUEST_ASSIGNED or request.assigned_offer_id is None:
        raise InvalidTechTransition("not_assigned")
    offer = db.get(TechOffer, request.assigned_offer_id)
    if offer is None:  # pragma: no cover — FK
        raise InvalidTechTransition("not_assigned")

    review = TechReview(
        request_id=request.id,
        profile_id=offer.profile_id,
        company_id=request.company_id,
        rating=rating,
        text=text,
        created_by_user_account_id=account.id,
    )
    db.add(review)
    request.status = REQUEST_COMPLETED
    request.completed_at = utcnow()
    db.flush()

    avg, count = db.execute(
        sa.select(sa.func.avg(TechReview.rating), sa.func.count()).where(
            TechReview.profile_id == offer.profile_id
        )
    ).one()
    profile = db.get(TechnologistProfile, offer.profile_id)
    if profile is not None:
        profile.rating_count = int(count)
        profile.rating_avg = decimal.Decimal(str(avg)).quantize(decimal.Decimal("0.01"))
    _audit(db, "tech_request.complete", request.id, {"rating": rating, "account_id": account.id})
    db.flush()
    return review


def review_for(db: Session, request_id: int) -> TechReview | None:
    return db.execute(
        sa.select(TechReview).where(TechReview.request_id == request_id)
    ).scalar_one_or_none()


# ── Threads ──────────────────────────────────────────────────────────────────


def thread_for(db: Session, request_id: int, profile_id: int) -> TechThread | None:
    return db.execute(
        sa.select(TechThread).where(
            TechThread.request_id == request_id, TechThread.profile_id == profile_id
        )
    ).scalar_one_or_none()


def open_thread(db: Session, request: TechRequest, profile: TechnologistProfile) -> TechThread:
    """The expert's side: idempotent get-or-create on a request they may read."""
    if not _expert_can_read(db, request, profile):
        raise TechRequestNotFound(str(request.id))
    return _get_or_create_thread(db, request.id, profile.id)


def open_thread_as_company(db: Session, request: TechRequest, profile_id: int) -> TechThread:
    """The factory's side: only with an expert who offered or was invited —
    a factory cannot cold-message the whole catalog through a request."""
    existing = thread_for(db, request.id, profile_id)
    if existing is not None:
        return existing
    has_offer = my_offer(db, request.id, profile_id) is not None
    if not has_offer and profile_id not in invited_profile_ids(db, request.id):
        raise TechRequestNotFound(str(profile_id))
    return _get_or_create_thread(db, request.id, profile_id)


def _get_or_create_thread(db: Session, request_id: int, profile_id: int) -> TechThread:
    existing = thread_for(db, request_id, profile_id)
    if existing is not None:
        return existing
    thread = TechThread(request_id=request_id, profile_id=profile_id)
    db.add(thread)
    db.flush()
    return thread


def _thread_and_request(db: Session, thread_id: int) -> tuple[TechThread, TechRequest]:
    thread = db.get(TechThread, thread_id)
    if thread is None:
        raise TechRequestNotFound(str(thread_id))
    request = db.get(TechRequest, thread.request_id)
    if request is None:  # pragma: no cover — FK
        raise TechRequestNotFound(str(thread_id))
    return thread, request


def get_thread_for_expert(
    db: Session, profile: TechnologistProfile, thread_id: int
) -> tuple[TechThread, TechRequest]:
    thread, request = _thread_and_request(db, thread_id)
    if thread.profile_id != profile.id:
        raise TechRequestNotFound(str(thread_id))
    return thread, request


def get_thread_for_company(
    db: Session, account: UserAccount, company_id: int, thread_id: int
) -> tuple[TechThread, TechRequest]:
    """`CompanyNotFound` for a non-member; `TechRequestNotFound` for a thread
    on another company's request."""
    company = company_service.get_company_for(db, account, company_id)
    thread, request = _thread_and_request(db, thread_id)
    if request.company_id != company.id:
        raise TechRequestNotFound(str(thread_id))
    return thread, request


def threads_for_expert(db: Session, profile_id: int) -> list[TechThread]:
    return list(
        db.execute(
            sa.select(TechThread)
            .where(TechThread.profile_id == profile_id)
            .order_by(TechThread.updated_at.desc())
        ).scalars()
    )


def threads_for_request(db: Session, request_id: int) -> list[TechThread]:
    return list(
        db.execute(
            sa.select(TechThread)
            .where(TechThread.request_id == request_id)
            .order_by(TechThread.updated_at.desc())
        ).scalars()
    )


def post_message(
    db: Session,
    thread: TechThread,
    *,
    author_kind: str,
    account: UserAccount,
    body: str = "",
    file_content: bytes | None = None,
    file_name: str | None = None,
) -> TechMessage:
    if author_kind not in (AUTHOR_COMPANY, AUTHOR_TECHNOLOGIST):
        raise ValueError("bad_author_kind")
    text = (body or "").strip()
    if not text and file_content is None:
        raise ValueError("empty_message")

    storage_path: str | None = None
    if file_content is not None:
        if len(file_content) > MAX_CHAT_FILE_BYTES:
            raise ValueError("file_too_large")
        storage_path, _mime = storage_service.store_tech_chat_file(
            thread.id, file_content, file_name or "attachment"
        )

    message = TechMessage(
        thread_id=thread.id,
        author_kind=author_kind,
        author_account_id=account.id,
        body=text,
        file_storage_path=storage_path,
        file_name=file_name if storage_path else None,
    )
    db.add(message)
    thread.updated_at = utcnow()
    db.flush()
    return message


def list_messages(
    db: Session, thread: TechThread, *, after_id: int | None = None, limit: int = 100
) -> list[TechMessage]:
    stmt = sa.select(TechMessage).where(TechMessage.thread_id == thread.id)
    if after_id is not None:
        stmt = stmt.where(TechMessage.id > after_id)
    return list(db.execute(stmt.order_by(TechMessage.id).limit(max(1, min(limit, 200)))).scalars())
