"""Supplier responses to buyer RFQs (R4 / P2 — T1.3 + T1.35).

A buyer's `Request` doubles as an RFQ. Verified supplier companies quote against
it (price / quantity / lead time); the buyer accepts one, which opens the Deal
and retires the rest. Acceptance itself lives in `deal_service` — this module
owns who may quote, and on which RFQs.

**Visibility (FR-D10).** An RFQ carries commercial intent, so it defaults to
`verified_only`. `is_visible_to` is the single rule, and `list_open_requests`
is its SQL twin: the market list and the submit guard must agree, or the UI
shows a "Respond" button the API then refuses.
"""

from __future__ import annotations

import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyMember
from app.models.deals import RfqResponse
from app.models.enums import (
    CompanyMemberStatus,
    CompanyStatus,
    PriceBasis,
    RequestStatus,
    RfqResponseStatus,
    RfqVisibility,
)
from app.models.requests import Request
from app.services import audit_service, event_service, event_types, notification_service
from app.services.deal_service import CompanyNotVerified, ResponseNotOpen

logger = logging.getLogger(__name__)

#: RFQ statuses that still accept supplier quotes. A request is live from the
#: moment it is filed until the team closes, cancels or matches it — there is no
#: separate "published" state in `RequestStatus`.
OPEN_STATUSES: frozenset[RequestStatus] = frozenset(
    {
        RequestStatus.new,
        RequestStatus.viewed,
        RequestStatus.in_progress,
        RequestStatus.offer_sent,
    }
)


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class CannotRespondOwnRequest(Exception):
    """A company may not quote against its own RFQ."""


class AlreadyResponded(Exception):
    """This company already has a live response to this RFQ."""


class RfqNotVisible(Exception):
    """The RFQ is not visible to this company (verified gate / selected list)."""


class RequestNotOpen(Exception):
    """The RFQ no longer accepts responses."""


class NotResponseAuthor(Exception):
    """Only the company that filed a response may withdraw it."""


# ── Visibility ────────────────────────────────────────────────────────────────


def is_visible_to(request: Request, company: Company) -> bool:
    """Whether `company` may see (and therefore answer) this RFQ.

    Mirrors `list_open_requests`. A company never "sees" its own RFQ through
    this gate — that is the buyer's own view, handled elsewhere.
    """
    if request.visibility == RfqVisibility.all:
        return True
    if request.visibility == RfqVisibility.selected:
        allowed = request.visible_company_ids or []
        return company.id in {int(x) for x in allowed}
    return company.status == CompanyStatus.verified


def visibility_clause(company: Company) -> ColumnElement[bool]:
    """`is_visible_to` as SQL, for the paginated market list.

    Note the shape: `verified_only` tests the VIEWER's status, which is a plain
    Python boolean here, not a column — so the whole rule is one indexable
    predicate rather than a post-filter.
    """
    viewer_is_verified = company.status == CompanyStatus.verified
    return sa.or_(
        Request.visibility == RfqVisibility.all,
        sa.and_(
            Request.visibility == RfqVisibility.verified_only,
            sa.literal(viewer_is_verified),
        ),
        sa.and_(
            Request.visibility == RfqVisibility.selected,
            Request.visible_company_ids.contains([company.id]),
        ),
    )


def list_open_requests(
    db: Session, company: Company, *, limit: int = 50, offset: int = 0
) -> list[Request]:
    """Open RFQs this supplier company may answer, newest first.

    Filtering happens in SQL so LIMIT/OFFSET page over the visible set — a
    Python post-filter would silently under-fill pages. Excludes the viewer's
    own RFQs: a company cannot quote against itself, so listing them is a dead
    end.
    """
    query: Query[Request] = (
        db.query(Request)
        .filter(
            Request.status.in_(list(OPEN_STATUSES)),
            Request.company_id.isnot(None),
            Request.company_id != company.id,
            visibility_clause(company),
        )
        .order_by(Request.created_at.desc(), Request.id.desc())
    )
    return query.limit(max(1, min(limit, 200))).offset(max(0, offset)).all()


# ── Submitting ────────────────────────────────────────────────────────────────


def submit(
    db: Session,
    request: Request,
    company: Company,
    account: UserAccount,
    *,
    price: decimal.Decimal,
    currency: str = "USD",
    qty: decimal.Decimal,
    qty_unit: str = "MT",
    incoterms: PriceBasis | None = None,
    lead_time_days: int | None = None,
    comment: str | None = None,
) -> RfqResponse:
    """File this company's quote against an RFQ.

    Guard order matters: own-request first (the buyer is looking at their own
    thing, not being denied access), then verified, then the seller-role gate
    (role_not_allowed reveals nothing about THIS request, so it may precede
    visibility), then visibility, then the open-status check.
    """
    from app.services import company_service  # noqa: PLC0415 — cycle-safe, keep local

    if request.company_id is not None and request.company_id == company.id:
        raise CannotRespondOwnRequest(str(request.id))
    if company.status != CompanyStatus.verified:
        raise CompanyNotVerified(str(company.id))
    company_service.require_business_role(company, company_service.SELLER_ROLES)
    if not is_visible_to(request, company):
        raise RfqNotVisible(str(request.id))
    if request.status not in OPEN_STATUSES:
        raise RequestNotOpen(str(request.status))

    response = RfqResponse(
        request_id=request.id,
        company_id=company.id,
        created_by_user_account_id=account.id,
        price=price,
        currency=(currency or "USD").upper()[:3],
        qty=qty,
        qty_unit=qty_unit or "MT",
        incoterms=incoterms,
        lead_time_days=lead_time_days,
        comment=(comment or "").strip() or None,
        status=RfqResponseStatus.submitted,
    )
    try:
        # The INSERT must happen INSIDE the savepoint: a unique violation on the
        # partial index would otherwise poison the caller's transaction and every
        # later statement would raise PendingRollbackError.
        with db.begin_nested():
            db.add(response)
            db.flush()
    except IntegrityError as exc:
        raise AlreadyResponded(str(company.id)) from exc

    event_service.emit(
        db, event_types.RFQ_RESPONSE_SUBMITTED, "rfq_response", response.id,
        {
            "request_id": request.id,
            "company_id": company.id,
            "buyer_company_id": request.company_id,
        },
    )
    audit_service.write_audit(
        db, None, "rfq_response.submit", "rfq_responses", str(response.id),
        {"account_id": account.id, "request_id": request.id, "company_id": company.id},
    )
    if request.company_id is not None:
        title_key, body_key = notification_service.keys_for(
            notification_service.KIND_RFQ_RESPONSE_NEW
        )
        notification_service.notify_company(
            db,
            request.company_id,
            kind=notification_service.KIND_RFQ_RESPONSE_NEW,
            title_key=title_key,
            body_key=body_key,
            params={"request_id": request.id, "number": request.number},
            entity="request",
            entity_id=str(request.id),
        )
    logger.info(
        "rfq_response_service.submit",
        extra={"response_id": response.id, "request_id": request.id, "company_id": company.id},
    )
    return response


def withdraw(db: Session, response: RfqResponse, account: UserAccount) -> RfqResponse:
    """Pull a quote back. Only before acceptance, and only by the author company."""
    member = (
        db.query(CompanyMember.id)
        .filter(
            CompanyMember.company_id == response.company_id,
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .first()
    )
    if member is None:
        raise NotResponseAuthor(str(response.id))
    if response.status != RfqResponseStatus.submitted:
        raise ResponseNotOpen(str(response.status))

    response.status = RfqResponseStatus.withdrawn
    db.flush()
    audit_service.write_audit(
        db, None, "rfq_response.withdraw", "rfq_responses", str(response.id),
        {"account_id": account.id, "request_id": response.request_id},
    )
    return response


# ── Reading ───────────────────────────────────────────────────────────────────


def list_for_request(
    db: Session, request: Request, *, viewer_company_id: int | None = None
) -> list[RfqResponse]:
    """Responses to an RFQ.

    `viewer_company_id` narrows the list to that company's own response — a
    supplier must never see a competitor's price. Pass None for the RFQ owner
    (and for staff), who see every quote.
    """
    query = db.query(RfqResponse).filter(RfqResponse.request_id == request.id)
    if viewer_company_id is not None:
        query = query.filter(RfqResponse.company_id == viewer_company_id)
    return query.order_by(RfqResponse.id).all()


def get_live_response(db: Session, request_id: int, company_id: int) -> RfqResponse | None:
    """This company's non-withdrawn response to an RFQ, if any."""
    return (
        db.query(RfqResponse)
        .filter(
            RfqResponse.request_id == request_id,
            RfqResponse.company_id == company_id,
            RfqResponse.status != RfqResponseStatus.withdrawn,
        )
        .first()
    )
