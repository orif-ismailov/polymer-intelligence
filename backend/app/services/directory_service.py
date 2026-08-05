"""Public company directories, keyed by confirmed business role.

The marketplace nav offers four directories (Производители · Трейдеры ·
Логистика · Лаборатории) and they are one query with one parameter, not four
surfaces. `manufacturer_service.list_manufacturers` predates this module and now
delegates here, so the manufacturers page and the three new ones cannot answer
the same question differently.

Two rules hold for every role, and they are the whole security posture of the
anonymous directory:

* **verified companies only.** A `draft` or `pending` company is a claim nobody
  has checked. It does not appear, the same way an unapproved offer does not.
* **confirmed roles only.** `declared` is what a company said about itself
  during registration; `confirmed` is what staff established during
  verification. A directory built on `declared` would let any registrant list
  itself as an accredited laboratory.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.models.companies import Company, CompanyBusinessRole
from app.models.enums import BusinessRoleStatus, CompanyStatus
from app.models.enums import CompanyBusinessRole as CompanyBusinessRoleEnum

#: The roles that get a public directory page. `importer`, `distributor` and
#: `insurance_provider` are real roles a company can confirm, but they have no
#: nav entry in the mockup and no page to land on, so they are not routable.
#: Keep this in sync with PUBLIC_DIRECTORIES in the portal's route table.
PUBLIC_DIRECTORY_ROLES: tuple[CompanyBusinessRoleEnum, ...] = (
    CompanyBusinessRoleEnum.manufacturer,
    CompanyBusinessRoleEnum.trader,
    CompanyBusinessRoleEnum.logistics_provider,
    CompanyBusinessRoleEnum.laboratory,
)


def _base_query(db: Session, role: CompanyBusinessRoleEnum) -> sa.orm.Query[Company]:
    role_exists = (
        db.query(CompanyBusinessRole.id)
        .filter(
            CompanyBusinessRole.company_id == Company.id,
            CompanyBusinessRole.role == role,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .exists()
    )
    return db.query(Company).filter(Company.status == CompanyStatus.verified, role_exists)


def list_by_role(
    db: Session,
    *,
    role: CompanyBusinessRoleEnum,
    q: str | None = None,
    country: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[Company], int]:
    """One page of verified companies holding ``role``, plus the total match count.

    Ordered by short name so the directory is stable between requests: an
    unordered page-2 can repeat a row from page 1, which on a crawlable
    directory means two URLs serving the same company.
    """
    query = _base_query(db, role).options(selectinload(Company.business_roles))
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            sa.or_(
                Company.legal_name.ilike(needle),
                Company.short_name.ilike(needle),
                Company.legal_address.ilike(needle),
            )
        )
    if country:
        query = query.filter(Company.jurisdiction == country.strip().upper())
    total = query.count()
    items = (
        query.order_by(Company.short_name.asc().nullslast(), Company.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def count_by_role(db: Session, role: CompanyBusinessRoleEnum) -> int:
    """How many verified companies hold ``role`` (the home page's tile counts)."""
    return _base_query(db, role).count()


def get_public_company(
    db: Session, company_id: int, *, role: CompanyBusinessRoleEnum | None = None
) -> Company | None:
    """A single verified company for an anonymous profile page, or None.

    Passing ``role`` scopes the lookup to one directory, so
    `/laboratories/{id}` cannot render a company that is only a trader. Without
    it the company is resolved across every directory role.
    """
    query = db.query(Company).options(selectinload(Company.business_roles))
    if role is not None:
        query = _base_query(db, role).options(selectinload(Company.business_roles))
    else:
        query = query.filter(Company.status == CompanyStatus.verified)
    return query.filter(Company.id == company_id).first()


def confirmed_roles(company: Company) -> list[str]:
    """The company's confirmed roles as plain strings (badge rows, JSON-LD)."""
    return [
        str(r.role) for r in company.business_roles if r.status == BusinessRoleStatus.confirmed
    ]
