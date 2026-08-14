"""
Company licences (P5 W3 — T3.2).

What a company is allowed to trade, per REGIME. The four Uzbek regimes have four
different licensors and four different document sets, so a licence without a
regime is not a fact a publish gate can act on.

Registration is a STAFF action taken while looking at the licence document the
company uploaded through the R1 verification flow — that review IS the approval,
so a registered licence is `active` immediately. `pending_review` stays in the
enum for a future self-service path where a company files its own licence and
waits.

Expiry is a date comparison at read time (`active_for`), never a swept status.
A nightly sweep would leave a window in which an expired licence still unlocks a
precursor sale, which is the exact failure this table exists to prevent.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.domains.compliance.models import CompanyLicense
from app.models.enums import LicenseStatus, RegulationRegime
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def _normalized(category: str | None) -> str | None:
    return category.strip().casefold() if category and category.strip() else None


def register(
    db: Session,
    *,
    company_id: int,
    regime: RegulationRegime,
    category: str | None = None,
    license_number: str | None = None,
    issued_by: str | None = None,
    issued_at: datetime.date | None = None,
    expires_at: datetime.date | None = None,
    document_id: int | None = None,
    note: str | None = None,
    staff_user_id: int | None,
) -> CompanyLicense:
    """Record a licence a company holds. Does NOT commit."""
    licence = CompanyLicense(
        company_id=company_id,
        regime=regime,
        category=category,
        license_number=license_number,
        issued_by=issued_by,
        issued_at=issued_at,
        expires_at=expires_at,
        document_id=document_id,
        note=note,
        status=LicenseStatus.active,
        registered_by=staff_user_id,
    )
    db.add(licence)
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="license.register",
        entity="company_licenses",
        entity_id=str(licence.id),
        details={
            "company_id": company_id,
            "regime": str(regime),
            "category": category,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    logger.info(
        "license.register",
        extra={"license_id": licence.id, "company_id": company_id, "regime": str(regime)},
    )
    return licence


def revoke(
    db: Session, licence: CompanyLicense, *, reason: str, staff_user_id: int | None
) -> CompanyLicense:
    """Withdraw a licence. Takes effect immediately. Does NOT commit."""
    licence.status = LicenseStatus.revoked
    licence.revoked_at = utcnow()
    licence.revoke_reason = reason
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="license.revoke",
        entity="company_licenses",
        entity_id=str(licence.id),
        details={"company_id": licence.company_id, "reason": reason},
    )
    logger.info("license.revoke", extra={"license_id": licence.id})
    return licence


def get(db: Session, license_id: int) -> CompanyLicense | None:
    return db.get(CompanyLicense, license_id)


def list_for(db: Session, company_id: int) -> list[CompanyLicense]:
    """Every licence a company has ever held, newest first (revoked ones too).

    History matters: staff answering "why was this offer public in March?" need
    to see the licence that has since been withdrawn.
    """
    return (
        db.query(CompanyLicense)
        .filter(CompanyLicense.company_id == company_id)
        .order_by(CompanyLicense.id.desc())
        .all()
    )


def active_for(
    db: Session,
    company_id: int,
    regime: RegulationRegime,
    *,
    category: str | None = None,
    today: datetime.date | None = None,
) -> CompanyLicense | None:
    """The company's live licence for a regime, or None.

    ``category`` is compared case-insensitively and only when the substance
    names one. A licence whose category is blank does NOT satisfy a categorised
    requirement — that hole is how a licence for one part of a regime would
    quietly cover the rest of it.
    """
    day = today or datetime.date.today()
    wanted = _normalized(category)
    rows = (
        db.query(CompanyLicense)
        .filter(
            CompanyLicense.company_id == company_id,
            CompanyLicense.regime == regime,
            CompanyLicense.status == LicenseStatus.active,
        )
        .order_by(CompanyLicense.id.desc())
        .all()
    )
    for licence in rows:
        if not licence.is_active_on(day):
            continue
        if wanted is not None and _normalized(licence.category) != wanted:
            continue
        return licence
    return None
