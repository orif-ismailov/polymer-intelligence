"""Company reviews — write, read, and the aggregate the directory prints.

Not moderated (see `0036`'s docstring): what bounds abuse is eligibility, checked
here — one row per company pair, author ≠ subject, both companies verified.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.enums import CompanyReviewStatus, CompanyStatus
from app.models.reviews import CompanyReview

logger = logging.getLogger(__name__)

#: How many reviews travel inline on a company's public payload.
#:
#: The whole first page rather than a separate endpoint: `PublicCompanyPage`
#: renders every tab panel into the SSR HTML (`renderAllPanels`) so a crawler
#: sees them, and a second request would either need its own `ssr/prefetch.ts`
#: entry or would server-render a spinner where the reviews should be.
PUBLIC_PAGE_SIZE = 20


class ReviewSubjectNotFound(Exception):
    """No verified company to review."""


class SelfReview(Exception):
    """A company cannot review itself."""


class DuplicateReview(Exception):
    """This company has already reviewed that one."""


def upsert_review(
    db: Session,
    *,
    subject: Company,
    author: Company,
    account: UserAccount,
    rating: int,
    body: str | None,
) -> CompanyReview:
    """Create or replace the author company's review of `subject`.

    Upsert rather than insert: the unique pair means a second submission is not a
    new fact but a changed opinion, and answering it with a 409 the UI has to
    explain would be pedantry. `DuplicateReview` stays for callers that want the
    distinction — nothing raises it today.

    Flushes; the caller owns the commit.
    """
    if subject.id == author.id:
        raise SelfReview(str(subject.id))

    existing = (
        db.query(CompanyReview)
        .filter(
            CompanyReview.company_id == subject.id,
            CompanyReview.author_company_id == author.id,
        )
        .first()
    )
    if existing is not None:
        existing.rating = rating
        existing.body = body
        existing.author_account_id = account.id
        # A takedown must not be undone by the author editing their text.
        db.flush()
        return existing

    review = CompanyReview(
        company_id=subject.id,
        author_company_id=author.id,
        author_account_id=account.id,
        rating=rating,
        body=body,
        status=CompanyReviewStatus.published,
    )
    db.add(review)
    db.flush()
    logger.info(
        "review_service.upsert_review",
        extra={"company_id": subject.id, "author_company_id": author.id},
    )
    return review


def get_reviewable_company(db: Session, company_id: int) -> Company:
    """The subject must be verified — the same bar as appearing in a directory."""
    company = db.get(Company, company_id)
    if company is None or company.status != CompanyStatus.verified:
        raise ReviewSubjectNotFound(str(company_id))
    return company


def list_published(
    db: Session, company_id: int, *, limit: int = PUBLIC_PAGE_SIZE, offset: int = 0
) -> list[CompanyReview]:
    return (
        db.query(CompanyReview)
        .filter(
            CompanyReview.company_id == company_id,
            CompanyReview.status == CompanyReviewStatus.published,
        )
        .order_by(CompanyReview.id.desc())
        .limit(max(1, min(limit, 100)))
        .offset(max(0, offset))
        .all()
    )


def rating_summary_for(
    db: Session, company_ids: list[int]
) -> dict[int, tuple[float, int]]:
    """`{company_id: (average, count)}` for published reviews — ONE query.

    Plural on purpose. `public._company_card` already runs `offer_count_for` once
    per row, so a directory page of 24 costs 24 queries; a per-company aggregate
    beside it would double that. Companies with no reviews are simply absent from
    the mapping rather than carrying a zero, so the caller can tell "not rated
    yet" from "rated zero" — which the star line has to say differently.
    """
    if not company_ids:
        return {}
    rows = (
        db.query(
            CompanyReview.company_id,
            sa.func.avg(CompanyReview.rating),
            sa.func.count(CompanyReview.id),
        )
        .filter(
            CompanyReview.company_id.in_(company_ids),
            CompanyReview.status == CompanyReviewStatus.published,
        )
        .group_by(CompanyReview.company_id)
        .all()
    )
    return {
        company_id: (round(float(average), 2), int(count))
        for company_id, average, count in rows
    }
