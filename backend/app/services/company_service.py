"""Company registry service (R1 W4 — T4.1).

Create/list/read companies (membership-scoped), edit the draft profile, declare
business roles, add (encrypted) bank accounts, and drive the company status machine.
Cross-context effects go through the outbox (`event_service.emit`); every
state-changing action writes an audit row (flush-only — the caller commits).

Identity is a portal `UserAccount` (not staff): those actions audit with
`staff_user_id=None` and the account id in `details`.
"""

from __future__ import annotations

import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_pii
from app.models.accounts import UserAccount
from app.models.companies import (
    Company,
    CompanyBankAccount,
    CompanyBusinessRole,
    CompanyMember,
)
from app.models.enums import (
    BankAccountStatus,
    BusinessRoleStatus,
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyStatus,
    VerificationCaseStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.models.verification import VerificationCase
from app.services import audit_service, event_service, event_types

# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class InvalidTaxId(Exception):
    """The tax id (STIR/INN) does not match the jurisdiction's format."""


class InvalidBankMfo(Exception):
    """The bank MFO is not a 5-digit code."""


class CompanyAlreadyRegistered(Exception):
    """A company with this (jurisdiction, tax_id) already exists."""


class CompanyNotFound(Exception):
    """No company with this id is visible to the account (404 — never reveal existence)."""


class ProfileNotEditable(Exception):
    """The company profile can't be edited in its current status."""


class IdentityLocked(Exception):
    """A requisite frozen by an E-IMZO signature (R3) cannot be edited by hand."""


class InvalidCompanyTransition(Exception):
    """The requested company status transition is not allowed."""


class LastOwnerRemoval(Exception):
    """Refusing to remove/demote the last active owner of a company."""


# ── Company status machine (data, per ARCHITECTURE §6) ────────────────────────

_TRANSITIONS: dict[CompanyStatus, set[CompanyStatus]] = {
    CompanyStatus.draft: {CompanyStatus.pending_verification},
    CompanyStatus.pending_verification: {
        CompanyStatus.verified,
        CompanyStatus.rejected,
        CompanyStatus.draft,  # case cancelled → back to draft
    },
    CompanyStatus.verified: {CompanyStatus.suspended},
    CompanyStatus.rejected: {CompanyStatus.draft},  # re-open → back to draft for editing
    CompanyStatus.suspended: {CompanyStatus.verified},  # reinstate
    CompanyStatus.liquidated: set(),
}


def transition(
    db: Session,
    company: Company,
    to: CompanyStatus,
    *,
    staff_user_id: int | None = None,
    actor: dict[str, object] | None = None,
) -> Company:
    """Move a company to `to` if the machine allows it; audit the change (flush-only)."""
    frm = company.status
    if to not in _TRANSITIONS.get(frm, set()):
        raise InvalidCompanyTransition(f"{frm} → {to}")
    company.status = to
    details: dict[str, object] = {"from": str(frm), "to": str(to)}
    if actor:
        details.update(actor)
    audit_service.write_audit(
        db, staff_user_id, "company.transition", "companies", str(company.id), details
    )
    db.flush()
    return company


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_tax_id(jurisdiction: str, tax_id: str) -> None:
    if jurisdiction == "UZ":
        if not (tax_id.isdigit() and len(tax_id) == 9):
            raise InvalidTaxId("UZ STIR must be exactly 9 digits")
    elif not tax_id:
        raise InvalidTaxId("tax id is required")


def _active_membership(db: Session, company_id: int, account_id: int) -> CompanyMember | None:
    return (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_account_id == account_id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .first()
    )


# ── Create / read ─────────────────────────────────────────────────────────────


def create_company(
    db: Session, account: UserAccount, jurisdiction: str, tax_id: str
) -> Company:
    """Register a company (creator becomes owner); emit COMPANY_REGISTERED + audit."""
    juris = (jurisdiction or "UZ").strip().upper()
    tax_id = tax_id.strip()
    _validate_tax_id(juris, tax_id)

    company = Company(
        jurisdiction=juris,
        tax_id=tax_id,
        status=CompanyStatus.draft,
        created_by_user_account_id=account.id,
    )
    try:
        # SAVEPOINT: add + flush INSIDE the nested tx so a unique-constraint
        # violation rolls back only the savepoint and leaves the session usable.
        with db.begin_nested():
            db.add(company)
            db.flush()
    except IntegrityError as exc:
        raise CompanyAlreadyRegistered(f"{juris}/{tax_id}") from exc

    db.add(
        CompanyMember(
            company_id=company.id,
            user_account_id=account.id,
            member_role=CompanyMemberRole.owner,
            status=CompanyMemberStatus.active,
        )
    )
    db.flush()

    event_service.emit(
        db, event_types.COMPANY_REGISTERED, "company", company.id,
        {"jurisdiction": juris, "tax_id": tax_id, "account_id": account.id},
    )
    audit_service.write_audit(
        db, None, "company.create", "companies", str(company.id),
        {"account_id": account.id, "jurisdiction": juris, "tax_id": tax_id},
    )
    return company


def list_my_companies(db: Session, account: UserAccount) -> list[Company]:
    """All companies the account is an active member of (newest first)."""
    return (
        db.query(Company)
        .join(CompanyMember, CompanyMember.company_id == Company.id)
        .filter(
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .order_by(Company.created_at.desc())
        .all()
    )


def get_company_for(db: Session, account: UserAccount, company_id: int) -> Company:
    """Return the company IFF the account is an active member — else CompanyNotFound.

    404 semantics: a non-member gets the same "not found" as a truly missing id, so
    company existence is never revealed to outsiders (IDOR-safe).
    """
    company = (
        db.query(Company)
        .join(CompanyMember, CompanyMember.company_id == Company.id)
        .filter(
            Company.id == company_id,
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .first()
    )
    if company is None:
        raise CompanyNotFound(str(company_id))
    return company


# ── Profile / roles / bank ────────────────────────────────────────────────────

_EDITABLE_FIELDS = frozenset(
    {"legal_name", "short_name", "legal_form", "legal_address", "director_name"}
)

# Requisites filled+frozen by an E-IMZO signature (R3): rejected once identity_locked.
_EIMZO_LOCKED_FIELDS = frozenset({"legal_name", "director_name"})


def _assert_profile_editable(db: Session, company: Company) -> None:
    """Editable only while draft, or while a submitted case is back in needs_info."""
    if company.status == CompanyStatus.draft:
        return
    if company.status == CompanyStatus.pending_verification:
        needs_info = (
            db.query(VerificationCase)
            .filter(
                VerificationCase.company_id == company.id,
                VerificationCase.status == VerificationCaseStatus.needs_info,
            )
            .first()
        )
        if needs_info is not None:
            return
    raise ProfileNotEditable(str(company.status))


def update_profile(
    db: Session, company: Company, account: UserAccount, **fields: object
) -> Company:
    """Patch declared profile fields (draft / needs_info only); emit COMPANY_PROFILE_UPDATED.

    Requisites frozen by an E-IMZO signature (R3) reject a hand PATCH: changing
    legal_name/director_name on an identity_locked company raises IdentityLocked.
    """
    _assert_profile_editable(db, company)
    if company.identity_locked:
        for key in _EIMZO_LOCKED_FIELDS:
            new_value = fields.get(key)
            if new_value is not None and new_value != getattr(company, key):
                raise IdentityLocked(key)
    changed: dict[str, object] = {}
    for key, value in fields.items():
        if key in _EDITABLE_FIELDS and value is not None:
            setattr(company, key, value)
            changed[key] = value
    if changed:
        db.flush()
        event_service.emit(
            db, event_types.COMPANY_PROFILE_UPDATED, "company", company.id,
            {"account_id": account.id, "fields": sorted(changed)},
        )
        audit_service.write_audit(
            db, None, "company.update_profile", "companies", str(company.id),
            {"account_id": account.id, "fields": sorted(changed)},
        )
    return company


def set_business_roles(
    db: Session, company: Company, roles: list[CompanyBusinessRoleEnum]
) -> list[CompanyBusinessRole]:
    """Replace the company's declared business roles with `roles` (deduped)."""
    for existing in list(company.business_roles):
        db.delete(existing)
    db.flush()

    created: list[CompanyBusinessRole] = []
    for role in dict.fromkeys(roles):  # dedupe, preserve order
        row = CompanyBusinessRole(
            company_id=company.id, role=role, status=BusinessRoleStatus.declared
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def add_bank_account(
    db: Session,
    company: Company,
    bank_mfo: str,
    account_number: str,
    *,
    bank_name: str | None = None,
    currency: str = "UZS",
) -> CompanyBankAccount:
    """Add a bank account — number is app-encrypted; only last4 stored in clear."""
    mfo = bank_mfo.strip()
    if not (mfo.isdigit() and len(mfo) == 5):
        raise InvalidBankMfo("MFO must be exactly 5 digits")
    number = "".join(ch for ch in account_number if ch.isdigit())
    if len(number) < 4:
        raise InvalidBankMfo("account number too short")

    row = CompanyBankAccount(
        company_id=company.id,
        bank_mfo=mfo,
        bank_name=bank_name,
        account_number_enc=encrypt_pii(number),
        account_last4=number[-4:],
        currency=(currency or "UZS").upper(),
        status=BankAccountStatus.unverified,
    )
    db.add(row)
    db.flush()
    audit_service.write_audit(
        db, None, "company.add_bank_account", "company_bank_accounts", str(row.id),
        {"company_id": company.id, "mfo": mfo, "last4": row.account_last4},
    )
    return row


# ── Membership guards (owner protection) ──────────────────────────────────────


def _active_owner_count(db: Session, company_id: int) -> int:
    return (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.member_role == CompanyMemberRole.owner,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .count()
    )


def _guard_last_owner(db: Session, member: CompanyMember) -> None:
    """Raise LastOwnerRemoval if removing/demoting `member` would leave no active owner."""
    if (
        member.member_role == CompanyMemberRole.owner
        and member.status == CompanyMemberStatus.active
        and _active_owner_count(db, member.company_id) <= 1
    ):
        raise LastOwnerRemoval(str(member.company_id))


def remove_member(db: Session, company: Company, account_id: int) -> None:
    """Deactivate a member (guards the last active owner)."""
    member = _active_membership(db, company.id, account_id)
    if member is None:
        return
    _guard_last_owner(db, member)
    member.status = CompanyMemberStatus.removed
    db.flush()


def set_member_role(
    db: Session, company: Company, account_id: int, role: CompanyMemberRole
) -> CompanyMember:
    """Change a member's role (guards demoting the last active owner)."""
    member = _active_membership(db, company.id, account_id)
    if member is None:
        raise CompanyNotFound(str(company.id))
    if role != CompanyMemberRole.owner:
        _guard_last_owner(db, member)
    member.member_role = role
    db.flush()
    return member


def suspend(db: Session, company: Company, staff_user_id: int | None) -> Company:
    """Suspend a verified company (→ suspended); emit COMPANY_SUSPENDED (archives offers)."""
    transition(db, company, CompanyStatus.suspended, staff_user_id=staff_user_id)
    event_service.emit(
        db, event_types.COMPANY_SUSPENDED, "company", company.id, {"company_id": company.id}
    )
    return company


def reinstate(db: Session, company: Company, staff_user_id: int | None) -> Company:
    """Reinstate a suspended company (→ verified); emit COMPANY_REINSTATED."""
    transition(db, company, CompanyStatus.verified, staff_user_id=staff_user_id)
    event_service.emit(
        db, event_types.COMPANY_REINSTATED, "company", company.id, {"company_id": company.id}
    )
    return company


def now_utc() -> datetime.datetime:
    """UTC now (module seam so verification_service can stamp verified_at consistently)."""
    return datetime.datetime.now(datetime.UTC)
