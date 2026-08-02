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
from sqlalchemy.orm import Session, selectinload

from app.core.time import to_display_tz, utcnow
from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyBusinessRole
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    LogisticsRequestStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.models.logistics import LogisticsRequest
from app.services import company_service, storage_service

logger = logging.getLogger(__name__)

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


# ── Logistics requests ────────────────────────────────────────────────────────


class LogisticsCompanyNotFound(Exception):
    """No verified company with a confirmed `logistics_provider` role."""


class NotLogisticsParticipant(Exception):
    """The acting company is neither the buyer nor the carrier on this request."""


class SelfLogisticsRequest(Exception):
    """A company cannot send itself a transport request."""


def generate_logistics_request_number(db: Session) -> str:
    """Next LRQ-YYYY-NNNNNN for the current year in Asia/Tashkent."""
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    seq_name = f"logistics_request_seq_{year}"
    # 35_000, not the 34_000 `generate_factory_rfq_number` holds: sharing the key
    # would make every factory RFQ and every logistics request in a given year
    # serialise against each other for no reason.
    db.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(year) + 35_000})
    db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))  # noqa: S608
    nextval: int = db.execute(sa.text(f"SELECT nextval('{seq_name}')")).scalar()  # type: ignore[assignment]
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


def get_verified_logistics_company(db: Session, company_id: int) -> Company:
    """The carrier a request may be addressed to.

    Same bar as the public directory (`directory_service._base_query`): verified,
    with the role CONFIRMED rather than merely declared. A request that could be
    sent to a self-declared carrier would let any company collect cargo details
    by ticking a box during registration.
    """
    company = (
        db.query(Company)
        .options(selectinload(Company.business_roles))
        .filter(Company.id == company_id)
        .first()
    )
    if (
        company is None
        or company.status != CompanyStatus.verified
        or not _is_confirmed_carrier(db, company.id)
    ):
        raise LogisticsCompanyNotFound(str(company_id))
    return company


def create_logistics_request(
    db: Session,
    *,
    buyer: Company,
    carrier: Company,
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
    """Record a buyer's transport request. Flushes; the caller owns the commit."""
    if buyer.id == carrier.id:
        raise SelfLogisticsRequest(str(buyer.id))

    request = LogisticsRequest(
        number=generate_logistics_request_number(db),
        buyer_company_id=buyer.id,
        logistics_company_id=carrier.id,
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
        # Snapshot: the account may change its phone, and the carrier needs the
        # number that was current when the request was sent.
        contact_phone=account.phone,
        status=LogisticsRequestStatus.submitted,
    )
    db.add(request)
    db.flush()
    logger.info(
        "logistics_service.create_logistics_request",
        extra={
            "request_id": request.id,
            "buyer_company_id": buyer.id,
            "logistics_company_id": carrier.id,
        },
    )
    return request


def get_logistics_request_for(
    db: Session, account: UserAccount, request_id: int, company_id: int
) -> LogisticsRequest:
    """One request, as seen by a company the account actually belongs to.

    `get_company_for` raises `CompanyNotFound` for a non-member, so an outsider
    gets 404 rather than a 403 that would confirm the request exists.
    """
    company = company_service.get_company_for(db, account, company_id)
    request = db.get(LogisticsRequest, request_id)
    if request is None:
        raise NotLogisticsParticipant(str(request_id))
    if company.id not in (request.buyer_company_id, request.logistics_company_id):
        raise NotLogisticsParticipant(str(request_id))
    return request


def list_logistics_requests_for(
    db: Session, company_id: int, *, side: str = "sent"
) -> list[LogisticsRequest]:
    """`sent` = requests this company raised; `incoming` = ones addressed to it.

    Takes a raw `company_id`: the router has already resolved membership through
    `_company_or_404`, and re-resolving here would make the 404 depend on which
    of two lookups ran first.
    """
    query = db.query(LogisticsRequest)
    if side == "incoming":
        query = query.filter(LogisticsRequest.logistics_company_id == company_id)
    else:
        query = query.filter(LogisticsRequest.buyer_company_id == company_id)
    return query.order_by(LogisticsRequest.id.desc()).all()
