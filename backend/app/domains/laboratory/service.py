"""Laboratory directory surface: profile projection, the pool, and conversations.

Public surface: verified companies with a confirmed `laboratory` role. The
registration wizard captures a lab questionnaire into
`companies.laboratory_profile` (JSONB, migration 0033) — city, contacts,
description, and (0039) accreditations, methods and throughput stats.

Structured like `logistics_service`: the profile projection first, then the
request half. Deliberately NOT part of `lab_service`, which owns the staff-run
partner-lab orders (P6) — a different flow with a different audience that this
one does not touch.
"""

from __future__ import annotations

import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.time import to_display_tz, utcnow
from app.domains.companies import service as company_service
from app.domains.companies.models import Company, CompanyBusinessRole
from app.domains.laboratory.models import LabRequest, LabRequestMessage, LabRequestThread
from app.models.accounts import UserAccount
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    LabRequestStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.services import storage_service

logger = logging.getLogger(__name__)

#: Same ceiling as the other thread chats — one shared expectation of "a file".
MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024

#: Caps on the list fields, mirroring `schemas.portal_company.LaboratoryProfileIn`.
#: Applied again here because a row written before those caps existed — or by
#: anything other than that schema — must not make a public page arbitrarily long.
_MAX_METHODS = 48
_MAX_ACCREDITATIONS = 16


def _str_list(value: object, limit: int) -> list[str]:
    """Non-blank strings from a JSONB list, capped. Anything else reads empty."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:limit]


def _opt_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _opt_int(value: object, *, maximum: int) -> int | None:
    """A non-negative whole number, or None.

    `bool` is excluded explicitly: it is a subclass of `int` in Python, so a
    stray `true` would otherwise surface as «1 год на рынке».
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    if number < 0 or number > maximum:
        return None
    return number


def laboratory_profile_snippet(company: Company) -> dict[str, object] | None:
    """The public projection of `company.laboratory_profile`.

    Defensive on every key, like its logistics twin: the column is untyped JSONB
    written by a wizard that has already changed shape once, so a value of the
    wrong type is treated as absent rather than allowed to raise inside a
    response serializer.

    `None` — not an empty dict — when the company has no questionnaire at all, so
    the caller omits the whole block instead of rendering an empty card.
    """
    raw = company.laboratory_profile
    if not isinstance(raw, dict) or not raw:
        return None

    return {
        "city": _opt_str(raw.get("city")),
        "website": _opt_str(raw.get("website")),
        "description": _opt_str(raw.get("description")),
        "accreditations": _str_list(raw.get("accreditations"), _MAX_ACCREDITATIONS),
        "methods": _str_list(raw.get("methods"), _MAX_METHODS),
        # Bounded so a typo cannot print «Опыт работы: 99999 лет».
        "years_experience": _opt_int(raw.get("years_experience"), maximum=200),
        "studies_completed": _opt_int(raw.get("studies_completed"), maximum=100_000_000),
        "avg_turnaround_days": _opt_int(raw.get("avg_turnaround_days"), maximum=365),
    }


# ── Laboratory requests: the broadcast pool ───────────────────────────────────
#
# `is_visible_to` and `pool_clause` are TWINS and must stay that way. If the list
# query and the per-row guard ever disagree, the laboratory sees an «Ответить»
# button the API then refuses — the same trap `rfq_response_service` documents at
# the top of its module.
#
# Unlike the polymer RFQ pool, this one genuinely IS role-scoped: only a verified
# company with a CONFIRMED `laboratory` role may read what a buyer is testing
# and why.


#: Statuses a laboratory may still act on. `closed`/`rejected` drop out of the pool.
OPEN_STATUSES: tuple[LabRequestStatus, ...] = (
    LabRequestStatus.submitted,
    LabRequestStatus.viewed,
    LabRequestStatus.in_progress,
    LabRequestStatus.quoted,
)


class LaboratoryNotFound(Exception):
    """No verified company with a confirmed `laboratory` role."""


class NotLabParticipant(Exception):
    """The acting company is neither the buyer nor a laboratory on this request."""


class NotALaboratory(Exception):
    """The acting company may not read or answer the laboratory pool."""


def generate_lab_request_number(db: Session) -> str:
    """Next LBR-YYYY-NNNNNN for the current year in Asia/Tashkent.

    `LBR`, not `LAB`: `lab_service.generate_lab_number` already owns `LAB-` for
    the staff-run partner-lab orders, and the two flows run side by side.
    """
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    seq_name = f"lab_request_seq_{year}"
    # 39_000, not the 34_000 `generate_factory_rfq_number` holds: sharing the key
    # would make every factory RFQ and every logistics request in a given year
    # serialise against each other for no reason.
    db.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(year) + 39_000})
    db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))  # noqa: S608
    nextval: int = db.execute(sa.text(f"SELECT nextval('{seq_name}')")).scalar()  # type: ignore[assignment]
    return f"LBR-{year}-{nextval:06d}"


def _is_confirmed_lab(db: Session, company_id: int) -> bool:
    row = (
        db.query(CompanyBusinessRole.id)
        .filter(
            CompanyBusinessRole.company_id == company_id,
            CompanyBusinessRole.role == CompanyBusinessRoleEnum.laboratory,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .first()
    )
    return row is not None


def is_lab(db: Session, company: Company) -> bool:
    """Verified, with the laboratory role CONFIRMED rather than merely declared.

    `declared` is a tick-box during registration; treating it as sufficient would
    let anybody read every buyer's material and methods by claiming a role.
    """
    return company.status == CompanyStatus.verified and _is_confirmed_lab(
        db, company.id
    )


def list_lab_companies(db: Session) -> list[Company]:
    """Every company the pool is visible to — the broadcast's audience."""
    return (
        db.query(Company)
        .join(CompanyBusinessRole, CompanyBusinessRole.company_id == Company.id)
        .filter(
            Company.status == CompanyStatus.verified,
            CompanyBusinessRole.role == CompanyBusinessRoleEnum.laboratory,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .all()
    )


def is_visible_to(db: Session, request: LabRequest, company: Company) -> bool:
    """Whether `company` may see (and answer) this request as a LABORATORY.

    Mirrors `pool_clause`. A buyer never "sees" its own request through this
    gate — that is its own list, handled by `list_lab_requests_for`.
    """
    if request.buyer_company_id == company.id:
        return False
    if request.status not in OPEN_STATUSES:
        return False
    return is_lab(db, company)


def pool_clause(company: Company) -> ColumnElement[bool]:
    """`is_visible_to` as SQL, minus the role check.

    The role half is a plain Python boolean about the VIEWER, so the caller
    short-circuits on it instead of compiling it into the query — the same shape
    `rfq_response_service.visibility_clause` uses for `verified_only`, and it
    keeps this one predicate indexable by `ix_lab_requests_open`.
    """
    return sa.and_(
        LabRequest.status.in_(list(OPEN_STATUSES)),
        LabRequest.buyer_company_id != company.id,
    )


def list_open_requests_for_lab(
    db: Session, company: Company, *, limit: int = 50, offset: int = 0
) -> list[LabRequest]:
    """The pool, newest first. Empty for anyone who is not a laboratory.

    Filtering is in SQL so LIMIT/OFFSET page over the visible set; a Python
    post-filter would silently under-fill pages.
    """
    if not is_lab(db, company):
        return []
    return (
        db.query(LabRequest)
        .filter(pool_clause(company))
        .order_by(LabRequest.created_at.desc(), LabRequest.id.desc())
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
        .all()
    )


def create_lab_request(
    db: Session,
    *,
    buyer: Company,
    account: UserAccount,
    product_text: str,
    product_id: int | None = None,
    grade_text: str | None = None,
    study_type: str | None = None,
    methods: list[str] | None = None,
    sample_qty: str | None = None,
    comment: str | None = None,
    purpose: str | None = None,
    is_urgent: bool = False,
    desired_date: datetime.date | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> LabRequest:
    """Record a buyer's analysis request. Flushes; the caller owns the commit.

    No laboratory argument: the request is broadcast. Which labs end up reading it
    is decided at read time by `pool_clause`, so a laboratory verified tomorrow
    sees a request filed today.

    Contacts arrive from the FORM rather than the account — the sheet asks for
    all three, and `user_accounts` has a nullable name and no email column, so
    there would be nothing to snapshot them from.
    """
    request = LabRequest(
        number=generate_lab_request_number(db),
        buyer_company_id=buyer.id,
        created_by_user_account_id=account.id,
        product_id=product_id,
        product_text=product_text,
        grade_text=grade_text,
        study_type=study_type,
        methods=methods or [],
        sample_qty=sample_qty,
        comment=comment,
        purpose=purpose,
        is_urgent=is_urgent,
        desired_date=desired_date,
        contact_name=contact_name,
        contact_email=contact_email,
        # Falls back to the account's phone when the form left it blank: a lab
        # with no way to call back cannot answer at all.
        contact_phone=contact_phone or account.phone,
        status=LabRequestStatus.submitted,
    )
    db.add(request)
    db.flush()
    logger.info(
        "laboratory_service.create_lab_request",
        extra={"request_id": request.id, "buyer_company_id": buyer.id},
    )
    return request


def get_lab_request_for(
    db: Session, account: UserAccount, request_id: int, company_id: int
) -> LabRequest:
    """One request, as seen by the buyer who filed it or by any laboratory.

    `get_company_for` raises `CompanyNotFound` for a non-member, so an outsider
    gets 404 rather than a 403 that would confirm the request exists.
    """
    company = company_service.get_company_for(db, account, company_id)
    request = db.get(LabRequest, request_id)
    if request is None:
        raise NotLabParticipant(str(request_id))
    if request.buyer_company_id == company.id:
        return request
    if is_visible_to(db, request, company):
        return request
    raise NotLabParticipant(str(request_id))


def list_lab_requests_for(
    db: Session, company_id: int
) -> list[LabRequest]:
    """A buyer company's own requests, newest first.

    The laboratory side is the POOL — a different question with a different
    predicate, not a `side=` flag on this one.
    """
    return (
        db.query(LabRequest)
        .filter(LabRequest.buyer_company_id == company_id)
        .order_by(LabRequest.id.desc())
        .all()
    )


# ── Conversations ─────────────────────────────────────────────────────────────


def thread_party_role(
    thread: LabRequestThread, request: LabRequest, company_id: int
) -> str | None:
    """`"buyer"` / `"laboratory"` / None.

    Takes the request as well as the thread because the buyer side is not stored
    on the thread — it is `request.buyer_company_id`, and duplicating it would be
    a second place for the same fact to go wrong.
    """
    if company_id == thread.laboratory_company_id:
        return "laboratory"
    if company_id == request.buyer_company_id:
        return "buyer"
    return None


def open_or_get_thread(
    db: Session, *, request: LabRequest, laboratory: Company, account: UserAccount
) -> LabRequestThread:
    """Idempotent get-or-create of a laboratory's conversation on a request.

    Idempotent because the client calls it every time the chat screen mounts —
    the laboratory taps «Ответить» and should land in the same room each time.
    """
    existing = (
        db.query(LabRequestThread)
        .filter(
            LabRequestThread.lab_request_id == request.id,
            LabRequestThread.laboratory_company_id == laboratory.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    thread = LabRequestThread(
        lab_request_id=request.id,
        laboratory_company_id=laboratory.id,
        created_by_user_account_id=account.id,
    )
    db.add(thread)
    db.flush()
    logger.info(
        "laboratory_service.open_thread",
        extra={"request_id": request.id, "laboratory_company_id": laboratory.id},
    )
    return thread


def get_thread_for(
    db: Session, account: UserAccount, thread_id: int, company_id: int
) -> tuple[LabRequestThread, LabRequest]:
    """A thread and its request, for a company that is actually in it.

    A laboratory sees ONLY its own thread: another lab's conversation on the same
    request is invisible, which is the whole reason threads are per-laboratory
    rather than one room on the request.
    """
    company = company_service.get_company_for(db, account, company_id)
    thread = db.get(LabRequestThread, thread_id)
    if thread is None:
        raise NotLabParticipant(str(thread_id))
    request = db.get(LabRequest, thread.lab_request_id)
    if request is None:  # pragma: no cover — FK guarantees it
        raise NotLabParticipant(str(thread_id))
    if thread_party_role(thread, request, company.id) is None:
        raise NotLabParticipant(str(thread_id))
    return thread, request


def list_threads_for_request(
    db: Session, request_id: int
) -> list[LabRequestThread]:
    """Every laboratory conversation on one request — the BUYER's view."""
    return (
        db.query(LabRequestThread)
        .filter(LabRequestThread.lab_request_id == request_id)
        .order_by(LabRequestThread.updated_at.desc())
        .all()
    )


def list_threads_for_company(
    db: Session, company_id: int
) -> list[LabRequestThread]:
    """Both sides at once: threads this company answers, plus those on its own requests."""
    own_request_ids = (
        sa.select(LabRequest.id)
        .where(LabRequest.buyer_company_id == company_id)
        .scalar_subquery()
    )
    return (
        db.query(LabRequestThread)
        .filter(
            sa.or_(
                LabRequestThread.laboratory_company_id == company_id,
                LabRequestThread.lab_request_id.in_(own_request_ids),
            )
        )
        .order_by(LabRequestThread.updated_at.desc())
        .all()
    )


def post_message(
    db: Session,
    thread: LabRequestThread,
    account: UserAccount,
    company: Company,
    body: str = "",
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
) -> LabRequestMessage:
    """Append one message. Flushes; the caller owns the commit."""
    text = (body or "").strip()
    if not text and file_content is None:
        raise ValueError("empty_message")

    storage_path: str | None = None
    if file_content is not None:
        if len(file_content) > MAX_CHAT_FILE_BYTES:
            raise ValueError("file_too_large")
        storage_path, _mime = storage_service.store_lab_chat_file(
            thread.id, file_content, file_name or "attachment"
        )

    message = LabRequestMessage(
        thread_id=thread.id,
        author_account_id=account.id,
        author_company_id=company.id,
        body=text,
        file_storage_path=storage_path,
        file_name=file_name if storage_path else None,
    )
    db.add(message)
    # Bumped so `list_threads_for_company`'s ordering means "most recent
    # activity" rather than "most recently opened".
    thread.updated_at = utcnow()
    db.flush()
    return message


def list_messages(
    db: Session, thread: LabRequestThread, *, after_id: int | None = None, limit: int = 100
) -> list[LabRequestMessage]:
    """Append-only, so `after_id` is a safe delta cursor for the client's poll."""
    query = db.query(LabRequestMessage).filter(
        LabRequestMessage.thread_id == thread.id
    )
    if after_id is not None:
        query = query.filter(LabRequestMessage.id > after_id)
    return query.order_by(LabRequestMessage.id).limit(max(1, min(limit, 200))).all()
