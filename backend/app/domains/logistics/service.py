"""Logistics-provider directory surface.

Public surface: verified companies with a confirmed `logistics_provider` role.
The registration wizard captures a carrier questionnaire into
`companies.logistics_profile` (JSONB, migration 0032) — services, geography,
cargo specialisation, capabilities and a tariff model. Until now nothing read
it back out on the public side: `public._company_card` built every directory row
from `manufacturer_service.profile_snippet`, so a carrier's public page showed
blank *manufacturer* fields and none of what it had actually filled in.

This module owns the read side of that blob.
"""

from __future__ import annotations

import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core import numbering
from app.core.time import to_display_tz, utcnow
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company, CompanyBusinessRole
from app.domains.logistics.models import (
    LogisticsRequest,
    LogisticsRequestMessage,
    LogisticsRequestThread,
)
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    LogisticsRequestStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.services import storage_service

logger = logging.getLogger(__name__)

#: Same ceiling as the manufacturer chat — one shared expectation of "a file".
MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024

#: Caps on the list fields, mirroring the write-side limits in
#: `schemas.portal_company.LogisticsProfileIn`. Applied again here because a row
#: written before those caps existed — or by anything other than that schema —
#: must not be able to make a public page arbitrarily long.
_MAX_SERVICES = 32
_MAX_COUNTRIES = 64
_MAX_ROUTES = 64
_MAX_CARGO = 32
_MAX_CAPABILITIES = 32


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
    stray `true` in the blob would otherwise surface as «Опыт работы: 1 год».
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    if number < 0 or number > maximum:
        return None
    return number


def _capability_images(company: Company, raw: object) -> dict[str, str]:
    """`{capability_key: media_id}` → `{capability_key: url}`.

    Ids are resolved to URLs here rather than shipped raw: a media id is an
    internal handle, and the client would otherwise have to know how to build the
    proxy path. A non-integer value is dropped instead of raising — the blob is
    untyped JSONB and one bad key must not 500 a directory page.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, media_id in raw.items():
        if isinstance(media_id, bool) or not isinstance(media_id, int):
            continue
        out[str(key)] = storage_service.company_media_url(company.id, media_id)
    return out


def logistics_profile_snippet(company: Company) -> dict[str, object] | None:
    """The public projection of `company.logistics_profile`.

    Defensive on every key, like `manufacturer_service.profile_snippet`: the
    column is untyped JSONB written by a wizard that has already changed shape
    once, so a value of the wrong type is treated as absent rather than allowed
    to raise inside a response serializer.

    Returns `None` — not an empty dict — when the company has no carrier
    questionnaire at all, so the caller can omit the whole block instead of
    rendering an empty card. A profile that exists but is blank still returns a
    dict: that is a carrier who reached the step and skipped it, which is a
    different fact from "not a carrier".
    """
    raw = company.logistics_profile
    if not isinstance(raw, dict) or not raw:
        return None

    return {
        "city": _opt_str(raw.get("city")),
        "description": _opt_str(raw.get("description")),
        "services": _str_list(raw.get("services"), _MAX_SERVICES),
        "from_countries": _str_list(raw.get("from_countries"), _MAX_COUNTRIES),
        "to_countries": _str_list(raw.get("to_countries"), _MAX_COUNTRIES),
        "popular_routes": _str_list(raw.get("popular_routes"), _MAX_ROUTES),
        "cargo_types": _str_list(raw.get("cargo_types"), _MAX_CARGO),
        "capabilities": _str_list(raw.get("capabilities"), _MAX_CAPABILITIES),
        "tariff_model": _opt_str(raw.get("tariff_model")),
        # Bounded so a typo in the wizard cannot print «Опыт работы: 99999 лет».
        "years_experience": _opt_int(raw.get("years_experience"), maximum=200),
        "projects_completed": _opt_int(raw.get("projects_completed"), maximum=10_000_000),
        "capability_images": _capability_images(company, raw.get("capability_images")),
    }


# ── Logistics requests: the broadcast pool ───────────────────────────────────
#
# `is_visible_to` and `pool_clause` are TWINS and must stay that way. If the list
# query and the per-row guard ever disagree, the carrier sees an «Ответить»
# button the API then refuses — the same trap `rfq_response_service` documents at
# the top of its module.
#
# Unlike the polymer RFQ pool, this one genuinely IS role-scoped: only a verified
# company with a CONFIRMED `logistics_provider` role may read a shipper's cargo
# and route.


#: Statuses a carrier may still act on. `closed`/`rejected` drop out of the pool.
OPEN_STATUSES: tuple[LogisticsRequestStatus, ...] = (
    LogisticsRequestStatus.submitted,
    LogisticsRequestStatus.viewed,
    LogisticsRequestStatus.in_progress,
    LogisticsRequestStatus.quoted,
)


class LogisticsCompanyNotFound(Exception):
    """No verified company with a confirmed `logistics_provider` role."""


class NotLogisticsParticipant(Exception):
    """The acting company is neither the buyer nor a carrier on this request."""


class NotACarrier(Exception):
    """The acting company may not read or answer the carrier pool."""


def generate_logistics_request_number(db: Session) -> str:
    """Next LRQ-YYYY-NNNNNN for the current year in Asia/Tashkent."""
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    nextval = numbering.next_in_sequence(
        db,
        f"logistics_request_seq_{year}",
        numbering.LOCK_BASE_LOGISTICS_REQUEST + int(year),
    )
    return f"LRQ-{year}-{nextval:06d}"


def _is_confirmed_carrier(db: Session, company_id: int) -> bool:
    row = (
        db.query(CompanyBusinessRole.id)
        .filter(
            CompanyBusinessRole.company_id == company_id,
            CompanyBusinessRole.role == CompanyBusinessRoleEnum.logistics_provider,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .first()
    )
    return row is not None


def is_carrier(db: Session, company: Company) -> bool:
    """Verified, with the logistics role CONFIRMED rather than merely declared.

    `declared` is a tick-box during registration; treating it as sufficient would
    let anybody read every shipper's cargo and route by claiming a role.
    """
    return company.status == CompanyStatus.verified and _is_confirmed_carrier(
        db, company.id
    )


def list_carrier_companies(db: Session) -> list[Company]:
    """Every company the pool is visible to — the broadcast's audience."""
    return (
        db.query(Company)
        .join(CompanyBusinessRole, CompanyBusinessRole.company_id == Company.id)
        .filter(
            Company.status == CompanyStatus.verified,
            CompanyBusinessRole.role == CompanyBusinessRoleEnum.logistics_provider,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .all()
    )


def is_visible_to(db: Session, request: LogisticsRequest, company: Company) -> bool:
    """Whether `company` may see (and answer) this request as a CARRIER.

    Mirrors `pool_clause`. A buyer never "sees" its own request through this
    gate — that is its own list, handled by `list_logistics_requests_for`.
    """
    if request.buyer_company_id == company.id:
        return False
    if request.status not in OPEN_STATUSES:
        return False
    return is_carrier(db, company)


def pool_clause(company: Company) -> ColumnElement[bool]:
    """`is_visible_to` as SQL, minus the role check.

    The role half is a plain Python boolean about the VIEWER, so the caller
    short-circuits on it instead of compiling it into the query — the same shape
    `rfq_response_service.visibility_clause` uses for `verified_only`, and it
    keeps this one predicate indexable by `ix_logistics_requests_open`.
    """
    return sa.and_(
        LogisticsRequest.status.in_(list(OPEN_STATUSES)),
        LogisticsRequest.buyer_company_id != company.id,
    )


def list_open_requests_for_carrier(
    db: Session, company: Company, *, limit: int = 50, offset: int = 0
) -> list[LogisticsRequest]:
    """The pool, newest first. Empty for anyone who is not a carrier.

    Filtering is in SQL so LIMIT/OFFSET page over the visible set; a Python
    post-filter would silently under-fill pages.
    """
    if not is_carrier(db, company):
        return []
    return (
        db.query(LogisticsRequest)
        .filter(pool_clause(company))
        .order_by(LogisticsRequest.created_at.desc(), LogisticsRequest.id.desc())
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
        .all()
    )


def create_logistics_request(
    db: Session,
    *,
    buyer: Company,
    account: UserAccount,
    cargo_name: str,
    volume: decimal.Decimal,
    volume_unit: str,
    packaging_type: str | None,
    special_requirements: str | None,
    from_country: str,
    from_city: str | None,
    to_country: str,
    to_city: str | None,
) -> LogisticsRequest:
    """Record a buyer's transport request. Flushes; the caller owns the commit.

    No carrier argument: the request is broadcast. Which firms end up reading it
    is decided at read time by `pool_clause`, so a carrier verified tomorrow sees
    a request filed today.
    """
    request = LogisticsRequest(
        number=generate_logistics_request_number(db),
        buyer_company_id=buyer.id,
        created_by_user_account_id=account.id,
        cargo_name=cargo_name,
        volume=volume,
        volume_unit=volume_unit,
        packaging_type=packaging_type,
        special_requirements=special_requirements,
        from_country=from_country,
        from_city=from_city,
        to_country=to_country,
        to_city=to_city,
        # Snapshot: the account may change its phone, and a carrier needs the
        # number that was current when the request was sent.
        contact_phone=account.phone,
        status=LogisticsRequestStatus.submitted,
    )
    db.add(request)
    db.flush()
    logger.info(
        "logistics_service.create_logistics_request",
        extra={"request_id": request.id, "buyer_company_id": buyer.id},
    )
    return request


def get_logistics_request_for(
    db: Session, account: UserAccount, request_id: int, company_id: int
) -> LogisticsRequest:
    """One request, as seen by the buyer who filed it or by any carrier.

    `get_company_for` raises `CompanyNotFound` for a non-member, so an outsider
    gets 404 rather than a 403 that would confirm the request exists.
    """
    company = company_service.get_company_for(db, account, company_id)
    request = db.get(LogisticsRequest, request_id)
    if request is None:
        raise NotLogisticsParticipant(str(request_id))
    if request.buyer_company_id == company.id:
        return request
    if is_visible_to(db, request, company):
        return request
    raise NotLogisticsParticipant(str(request_id))


def list_logistics_requests_for(
    db: Session, company_id: int
) -> list[LogisticsRequest]:
    """A buyer company's own requests, newest first.

    No `side` parameter any more: the carrier side is the POOL, which is a
    different question with a different predicate.
    """
    return (
        db.query(LogisticsRequest)
        .filter(LogisticsRequest.buyer_company_id == company_id)
        .order_by(LogisticsRequest.id.desc())
        .all()
    )


# ── Conversations ─────────────────────────────────────────────────────────────


def thread_party_role(
    thread: LogisticsRequestThread, request: LogisticsRequest, company_id: int
) -> str | None:
    """`"buyer"` / `"carrier"` / None.

    Takes the request as well as the thread because the buyer side is not stored
    on the thread — it is `request.buyer_company_id`, and duplicating it would be
    a second place for the same fact to go wrong.
    """
    if company_id == thread.carrier_company_id:
        return "carrier"
    if company_id == request.buyer_company_id:
        return "buyer"
    return None


def open_or_get_thread(
    db: Session, *, request: LogisticsRequest, carrier: Company, account: UserAccount
) -> LogisticsRequestThread:
    """Idempotent get-or-create of a carrier's conversation on a request.

    Idempotent because the client calls it every time the chat screen mounts —
    the carrier taps «Ответить» and should land in the same room each time.
    """
    existing = (
        db.query(LogisticsRequestThread)
        .filter(
            LogisticsRequestThread.logistics_request_id == request.id,
            LogisticsRequestThread.carrier_company_id == carrier.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    thread = LogisticsRequestThread(
        logistics_request_id=request.id,
        carrier_company_id=carrier.id,
        created_by_user_account_id=account.id,
    )
    db.add(thread)
    db.flush()
    logger.info(
        "logistics_service.open_thread",
        extra={"request_id": request.id, "carrier_company_id": carrier.id},
    )
    return thread


def get_thread_for(
    db: Session, account: UserAccount, thread_id: int, company_id: int
) -> tuple[LogisticsRequestThread, LogisticsRequest]:
    """A thread and its request, for a company that is actually in it.

    A carrier sees ONLY its own thread: another carrier's conversation on the
    same request is invisible, which is the whole reason threads are per-carrier
    rather than one room on the request.
    """
    company = company_service.get_company_for(db, account, company_id)
    thread = db.get(LogisticsRequestThread, thread_id)
    if thread is None:
        raise NotLogisticsParticipant(str(thread_id))
    request = db.get(LogisticsRequest, thread.logistics_request_id)
    if request is None:  # pragma: no cover — FK guarantees it
        raise NotLogisticsParticipant(str(thread_id))
    if thread_party_role(thread, request, company.id) is None:
        raise NotLogisticsParticipant(str(thread_id))
    return thread, request


def list_threads_for_request(
    db: Session, request_id: int
) -> list[LogisticsRequestThread]:
    """Every carrier conversation on one request — the BUYER's view."""
    return (
        db.query(LogisticsRequestThread)
        .filter(LogisticsRequestThread.logistics_request_id == request_id)
        .order_by(LogisticsRequestThread.updated_at.desc())
        .all()
    )


def list_threads_for_company(
    db: Session, company_id: int
) -> list[LogisticsRequestThread]:
    """Both sides at once: threads this company carries, plus those on its own requests."""
    own_request_ids = (
        sa.select(LogisticsRequest.id)
        .where(LogisticsRequest.buyer_company_id == company_id)
        .scalar_subquery()
    )
    return (
        db.query(LogisticsRequestThread)
        .filter(
            sa.or_(
                LogisticsRequestThread.carrier_company_id == company_id,
                LogisticsRequestThread.logistics_request_id.in_(own_request_ids),
            )
        )
        .order_by(LogisticsRequestThread.updated_at.desc())
        .all()
    )


def post_message(
    db: Session,
    thread: LogisticsRequestThread,
    account: UserAccount,
    company: Company,
    body: str = "",
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
) -> LogisticsRequestMessage:
    """Append one message. Flushes; the caller owns the commit."""
    text = (body or "").strip()
    if not text and file_content is None:
        raise ValueError("empty_message")

    storage_path: str | None = None
    if file_content is not None:
        if len(file_content) > MAX_CHAT_FILE_BYTES:
            raise ValueError("file_too_large")
        storage_path, _mime = storage_service.store_logistics_chat_file(
            thread.id, file_content, file_name or "attachment"
        )

    message = LogisticsRequestMessage(
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
    db: Session, thread: LogisticsRequestThread, *, after_id: int | None = None, limit: int = 100
) -> list[LogisticsRequestMessage]:
    """Append-only, so `after_id` is a safe delta cursor for the client's poll."""
    query = db.query(LogisticsRequestMessage).filter(
        LogisticsRequestMessage.thread_id == thread.id
    )
    if after_id is not None:
        query = query.filter(LogisticsRequestMessage.id > after_id)
    return query.order_by(LogisticsRequestMessage.id).limit(max(1, min(limit, 200))).all()
