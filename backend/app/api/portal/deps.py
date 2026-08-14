"""Shared portal-router helpers. Under /api/v1/portal.

These four guards are the portal's common entry sequence: resolve the company for
the calling account, then narrow by business role or company role, and translate a
rate-limit refusal into a response. Eleven routers across six bounded contexts use
them, which is why they live here rather than in whichever router happened to
define them first.

Shared kernel, same status as `app/api/deps.py`: this module stays in `app/api/`
permanently and is **not** moved into `app/domains/` by the domain reorg. Anything
that belongs to exactly one domain does not belong here.

The names are public (no leading underscore) because they are an imported surface —
a private name that eleven other modules import is only telling the reader something
untrue.

Order matters at the call site: `company_or_404` first, so that a non-member gets 404
and never learns the company exists; the role guards return 403 and therefore must
only ever run for someone already known to be a member.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.models.accounts import UserAccount
from app.models.enums import CompanyBusinessRole
from app.services import rate_limit


def rate_limited(exc: rate_limit.RateLimited) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Daily limit reached",
        headers={"Retry-After": str(exc.retry_after)},
    )


def company_or_404(db: Session, account: UserAccount, company_id: int) -> Company:
    try:
        return company_service.get_company_for(db, account, company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found") from exc


def require_business_role(company: Company, allowed: frozenset[CompanyBusinessRole]) -> None:
    """403 `role_not_allowed` unless the company's account type permits this flow.

    Call AFTER `company_or_404` (outsiders keep their 404). The typed-code shape
    mirrors `company_not_verified` so the portal can branch on it.
    """
    try:
        company_service.require_business_role(company, allowed)
    except company_service.RoleNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "role_not_allowed"}
        ) from exc


def require_company_admin(db: Session, account: UserAccount, company_id: int) -> None:
    """Owner/manager only. Call AFTER `company_or_404` so outsiders still get 404."""
    try:
        company_service.require_company_role(
            db, account, company_id, company_service.COMPANY_ADMIN_ROLES
        )
    except company_service.InsufficientCompanyRole as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_company_role"
        ) from exc
