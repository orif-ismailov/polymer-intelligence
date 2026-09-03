"""Supplier matching for RFQ push (R4 / P4 — T3.2).

Given a buyer's RFQ, find the verified supplier companies worth telling about it
and rank them. No LLM is involved: `request_analysis_service` turned out to have
no structural matcher (it aggregates signals as *context* for its prompt), so per
the plan the candidate set is built in SQL here.

**Candidates** are verified portal companies with a recent, approved offer that
matches the RFQ by product id, polymer type, or product text. Telegram sellers
are excluded — they have no portal account to notify — and so is the RFQ's own
author.

**Score** = (product match + verified + lab passport + freshness) x role
multiplier. The multiplier is the interesting part: it lets a manufacturer
matching on polymer type outrank a trader matching the exact product, because a
buyer would rather hear from the plant. Weights are module constants and the
ordering they produce is pinned by a table-driven test.

The lab-passport term went live with P6: a supplier whose matching listing
carries a laboratory passport scores `W_LAB_PASSPORT` higher than an otherwise
identical one. It counts the PASSPORT, not `lab_verified` — that is what the
weight is named for, and a buyer cares that an analysis exists, not who paid for
it. (P4 shipped the term wired but inert on purpose, so this landing did not
silently re-derive the whole ranking.)
"""

from __future__ import annotations

import datetime
import decimal
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.domains.companies.models import Company, CompanyBusinessRole
from app.domains.marketplace.models import SellerOffer, SellerOfferFile
from app.domains.requests.models import Request
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    OfferFileKind,
    SellerOfferStatus,
)
from app.models.enums import (
    CompanyBusinessRole as RoleEnum,
)

logger = logging.getLogger(__name__)

# ── Weights (module constants; the ORDERING they produce is what tests pin) ────

#: How well the supplier's listing matches what the buyer asked for.
W_PRODUCT_EXACT = decimal.Decimal("1.0")   # same catalog product id
W_PRODUCT_TYPE = decimal.Decimal("0.6")    # same polymer type
W_PRODUCT_TEXT = decimal.Decimal("0.4")    # free-text overlap only

W_VERIFIED = decimal.Decimal("0.2")
#: Live since P6: any matching listing of theirs carries a laboratory passport.
W_LAB_PASSPORT = decimal.Decimal("0.15")
W_FRESH_OFFER = decimal.Decimal("0.1")

_MATCH_WEIGHT: dict[str, decimal.Decimal] = {
    "product": W_PRODUCT_EXACT,
    "type": W_PRODUCT_TYPE,
    "text": W_PRODUCT_TEXT,
}

#: Who the supplier is, as a multiplier. A plant beats a reseller at equal match.
#: Roles that say nothing about supplying polymer (laboratory, logistics,
#: insurance) sit at 1.0 — they neither help nor hurt.
ROLE_MULTIPLIER: dict[str, decimal.Decimal] = {
    RoleEnum.manufacturer.value: decimal.Decimal("1.3"),
    RoleEnum.distributor.value: decimal.Decimal("1.2"),
    RoleEnum.importer.value: decimal.Decimal("1.1"),
    RoleEnum.trader.value: decimal.Decimal("1.0"),
}
_DEFAULT_MULTIPLIER = decimal.Decimal("1.0")

#: An offer older than this is not evidence that anyone still sells the stuff.
#: Operator-tunable via the `rfq_supplier_offer_max_age_days` runtime setting.
DEFAULT_OFFER_MAX_AGE_DAYS = 90


@dataclass(frozen=True)
class ScoredCompany:
    """A supplier worth telling about this RFQ, and why."""

    company_id: int
    score: decimal.Decimal
    rank: int
    #: 'product' | 'type' | 'text' — what actually matched.
    match_kind: str
    roles: tuple[str, ...]


def score_candidate(
    *,
    match_kind: str,
    verified: bool,
    fresh_offer: bool,
    roles: Sequence[str],
    has_lab_passport: bool = False,
) -> decimal.Decimal:
    """Score one candidate. Pure — no database, no clock.

    The best of a company's roles wins: a company that is both a trader and a
    manufacturer is, for this purpose, a manufacturer.
    """
    base = _MATCH_WEIGHT.get(match_kind, decimal.Decimal("0"))
    if verified:
        base += W_VERIFIED
    if has_lab_passport:
        base += W_LAB_PASSPORT
    if fresh_offer:
        base += W_FRESH_OFFER

    multiplier = max(
        (ROLE_MULTIPLIER.get(role, _DEFAULT_MULTIPLIER) for role in roles),
        default=_DEFAULT_MULTIPLIER,
    )
    return (base * multiplier).quantize(decimal.Decimal("0.01"))


def offer_max_age_days(db: Session) -> int:
    """Freshness window for a supplier's listing (runtime setting)."""
    from app.services import settings_service  # noqa: PLC0415

    try:
        return settings_service.get_int("rfq_supplier_offer_max_age_days")
    except KeyError:  # pragma: no cover — defensive: spec always present
        return DEFAULT_OFFER_MAX_AGE_DAYS


def match_suppliers(db: Session, request: Request) -> list[ScoredCompany]:
    """Verified supplier companies worth telling about this RFQ, best first.

    Returns [] when the RFQ carries nothing to match on: pushing it to everyone
    would be worse than pushing it to no one.
    """
    cutoff = utcnow() - datetime.timedelta(days=offer_max_age_days(db))
    match_clause, kind_case = _match_terms(request)
    if match_clause is None:
        return []

    # Does ANY of this company's matching listings carry a passport (P6)? Asked
    # in the same grouped pass rather than per candidate: a supplier with five
    # matching listings is still one supplier, and one analysis is enough.
    passport_exists = (
        db.query(SellerOfferFile.id)
        .filter(
            SellerOfferFile.offer_id == SellerOffer.id,
            SellerOfferFile.kind == OfferFileKind.lab_passport,
        )
        .exists()
    )

    rows = (
        db.query(
            SellerOffer.company_id.label("company_id"),
            sa.func.min(kind_case).label("match_rank"),
            sa.func.max(SellerOffer.published_at).label("latest"),
            sa.func.bool_or(passport_exists).label("lab_passport"),
        )
        .join(Company, Company.id == SellerOffer.company_id)
        .filter(
            SellerOffer.status == SellerOfferStatus.approved,
            SellerOffer.company_id.isnot(None),
            SellerOffer.company_id != request.company_id,
            Company.status == CompanyStatus.verified,
            SellerOffer.published_at.isnot(None),
            SellerOffer.published_at >= cutoff,
            match_clause,
        )
        # One row per company: a supplier with five matching listings is still
        # one supplier to notify.
        .group_by(SellerOffer.company_id)
        .all()
    )
    if not rows:
        return []

    roles_by_company = _confirmed_roles(db, [r.company_id for r in rows])
    kinds = {1: "product", 2: "type", 3: "text"}

    scored = [
        ScoredCompany(
            company_id=row.company_id,
            score=score_candidate(
                match_kind=kinds.get(int(row.match_rank), "text"),
                verified=True,               # the query already filtered on it
                fresh_offer=True,            # …and on the freshness window
                roles=roles_by_company.get(row.company_id, ()),
                has_lab_passport=bool(row.lab_passport),
            ),
            rank=0,                          # assigned after sorting
            match_kind=kinds.get(int(row.match_rank), "text"),
            roles=roles_by_company.get(row.company_id, ()),
        )
        for row in rows
    ]
    # Deterministic order: score desc, then company id, so equal scores do not
    # shuffle between runs (and the log's ranks stay reproducible).
    scored.sort(key=lambda c: (-c.score, c.company_id))
    ranked = [
        ScoredCompany(
            company_id=c.company_id,
            score=c.score,
            rank=index + 1,
            match_kind=c.match_kind,
            roles=c.roles,
        )
        for index, c in enumerate(scored)
    ]
    logger.info(
        "supplier_matching.matched",
        extra={"request_id": request.id, "candidates": len(ranked)},
    )
    return ranked


def _match_terms(
    request: Request,
) -> tuple[sa.ColumnElement[bool] | None, sa.Case[int]]:
    """The match predicate, plus a CASE ranking HOW each offer matched.

    Both are built from the same three terms so the score can never claim a
    stronger match than the filter actually allowed.
    """
    terms: list[sa.ColumnElement[bool]] = []
    branches: list[tuple[sa.ColumnElement[bool], int]] = []

    if request.product_id is not None:
        exact = SellerOffer.product_id == request.product_id
        terms.append(exact)
        branches.append((exact, 1))
    if request.polymer_type:
        by_type = SellerOffer.polymer_type.ilike(request.polymer_type.strip())
        terms.append(by_type)
        branches.append((by_type, 2))
    text = (request.product_text or "").strip()
    if text:
        like = f"%{text}%"
        by_text = sa.or_(
            SellerOffer.product_text.ilike(like),
            SellerOffer.grade_text.ilike(like),
        )
        terms.append(by_text)
        branches.append((by_text, 3))

    if not terms:
        return None, sa.case((sa.true(), 3), else_=3)
    return sa.or_(*terms), sa.case(*branches, else_=3)


def _confirmed_roles(db: Session, company_ids: list[int]) -> dict[int, tuple[str, ...]]:
    """Confirmed business roles per company — one query, not one per candidate."""
    if not company_ids:
        return {}
    rows = db.query(CompanyBusinessRole.company_id, CompanyBusinessRole.role).filter(
        CompanyBusinessRole.company_id.in_(company_ids),
        CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
    )
    out: dict[int, list[str]] = {}
    for company_id, role in rows:
        out.setdefault(company_id, []).append(str(role))
    return {k: tuple(v) for k, v in out.items()}
