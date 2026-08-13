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
import re

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

# ── Account-type exclusivity ──────────────────────────────────────────────────
#
# Registration picks ONE of five cards (`portal` ACCOUNT_TYPES). Each maps to a
# closed set of `company_business_role` values. A company may hold roles from at
# most one card — never manufacturer+trader, importer+distributor, etc.
# «Дистрибьютор/Трейдер» is the only card that declares two enum members; both
# together (or either alone) still count as that single account type.

ACCOUNT_TYPE_ROLE_SETS: tuple[frozenset[CompanyBusinessRoleEnum], ...] = (
    frozenset({CompanyBusinessRoleEnum.importer}),
    frozenset(
        {CompanyBusinessRoleEnum.distributor, CompanyBusinessRoleEnum.trader}
    ),
    frozenset({CompanyBusinessRoleEnum.manufacturer}),
    frozenset({CompanyBusinessRoleEnum.logistics_provider}),
    frozenset({CompanyBusinessRoleEnum.laboratory}),
)

# ── Business-role capability sets (role-based cabinet) ────────────────────────
#
# Which account types may drive which flows. The portal hides the same features
# (`entities/company/model/features.ts` mirrors these sets); the API is where it
# is enforced. Gates read the NON-REVOKED role set — `declared` counts, because
# a draft company's cabinet is already shaped by what it registered as, and
# requests/inquiries are open to unverified companies. `insurance_provider` is
# not gateable: a company holding only unknown roles falls back to the buyer
# view (fail open, matching the portal's RequireCompany philosophy).

GATEABLE_ROLES: frozenset[CompanyBusinessRoleEnum] = frozenset(
    {
        CompanyBusinessRoleEnum.manufacturer,
        CompanyBusinessRoleEnum.importer,
        CompanyBusinessRoleEnum.trader,
        CompanyBusinessRoleEnum.distributor,
        CompanyBusinessRoleEnum.logistics_provider,
        CompanyBusinessRoleEnum.laboratory,
    }
)

#: May publish/edit offers and answer RFQs.
SELLER_ROLES: frozenset[CompanyBusinessRoleEnum] = frozenset(
    {
        CompanyBusinessRoleEnum.manufacturer,
        CompanyBusinessRoleEnum.distributor,
        CompanyBusinessRoleEnum.trader,
    }
)

#: May buy: purchase requests, inquiries, samples, factory chat/RFQ.
#: Manufacturers keep the buy side (raw-material procurement).
BUYER_CAPABLE_ROLES: frozenset[CompanyBusinessRoleEnum] = frozenset(
    {
        CompanyBusinessRoleEnum.importer,
        CompanyBusinessRoleEnum.distributor,
        CompanyBusinessRoleEnum.trader,
        CompanyBusinessRoleEnum.manufacturer,
    }
)

#: May order a laboratory analysis — everyone but the laboratories themselves
#: (a carrier testing cargo is cross-service and legitimate).
LAB_ORDERING_ROLES: frozenset[CompanyBusinessRoleEnum] = BUYER_CAPABLE_ROLES | {
    CompanyBusinessRoleEnum.logistics_provider
}

#: May order shipping — everyone but the carriers themselves.
LOGISTICS_ORDERING_ROLES: frozenset[CompanyBusinessRoleEnum] = BUYER_CAPABLE_ROLES | {
    CompanyBusinessRoleEnum.laboratory
}

# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class InvalidTaxId(Exception):
    """The tax id (STIR/INN) does not match the jurisdiction's format."""


class InvalidJurisdiction(Exception):
    """The jurisdiction is not a 2-letter ISO country code.

    `companies.jurisdiction` is `varchar(2)`, so anything longer reached Postgres
    as a `DataError` and surfaced to the client as a 500.
    """


class InvalidBankMfo(Exception):
    """The bank MFO is not a 5-digit code."""


class InvalidBusinessRoles(Exception):
    """Roles span more than one registration account type (or none)."""


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


class InsufficientCompanyRole(Exception):
    """The member is active but their role does not permit this action."""


class RoleNotAllowed(Exception):
    """The company's business roles do not include this capability (403 role_not_allowed).

    A different axis from InsufficientCompanyRole: that one is about the PERSON's
    standing inside the company, this one about the COMPANY's account type.
    """


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


#: ASCII-only. `str.isdigit()` is True for Arabic-Indic (٩), superscript (⁹) and
#: fullwidth (９) digits, so it accepted "9-digit" STIRs that are not digits at
#: all. Worse, the (jurisdiction, tax_id) unique constraint compares bytes, so
#: those homoglyph forms slipped past the duplicate guard and one legal entity
#: could be registered several times over.
_UZ_TAX_ID_RE = re.compile(r"\A[0-9]{9}\Z")
#: `companies.jurisdiction` is varchar(2) — enforce that here, not in Postgres.
_JURISDICTION_RE = re.compile(r"\A[A-Z]{2}\Z")


def _validate_tax_id(jurisdiction: str, tax_id: str) -> None:
    if jurisdiction == "UZ":
        if not _UZ_TAX_ID_RE.match(tax_id):
            raise InvalidTaxId("UZ STIR must be exactly 9 digits")
    elif not tax_id:
        raise InvalidTaxId("tax id is required")


def _validate_jurisdiction(jurisdiction: str) -> None:
    if not _JURISDICTION_RE.match(jurisdiction):
        raise InvalidJurisdiction("jurisdiction must be a 2-letter country code")


def normalize_new_company(jurisdiction: str, tax_id: str) -> tuple[str, str]:
    """Normalize + validate registration input WITHOUT touching the database.

    Split out of `create_company` so the endpoint can reject malformed input
    before it spends the caller's daily quota: `enforce_daily` used to run first,
    so five STIR typos locked a legitimate user out of registering for a day.
    """
    juris = (jurisdiction or "UZ").strip().upper()
    tax = tax_id.strip()
    _validate_jurisdiction(juris)
    _validate_tax_id(juris, tax)
    return juris, tax


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
    juris, tax_id = normalize_new_company(jurisdiction, tax_id)

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
    {
        "legal_name",
        "short_name",
        "legal_form",
        "legal_address",
        "actual_address",
        "registration_number",
        "director_name",
        "registration_date",
        "manufacturer_profile",
        "logistics_profile",
        "laboratory_profile",
    }
)

# Requisites filled+frozen by an E-IMZO signature (R3): rejected once identity_locked.
_EIMZO_LOCKED_FIELDS = frozenset({"legal_name", "director_name"})


#: Case states in which the DECLARED profile is still the applicant's to correct.
#: A case that has not been decided yet has not been relied upon, so editing the
#: address / registration date / legal form is legitimate; the requisites an
#: E-IMZO signature froze stay protected separately by `IdentityLocked`.
#:
#: `pending_review` and `checks_running` are here because of the E-IMZO flow:
#: `eimzo_service.verify` treats the signature as the first-time submit, so a
#: signed company leaves `draft` on step 1 of the registration wizard — before the
#: wizard has even asked for the address. Excluding those two states made every
#: signed registration fail its step-5 profile PATCH with 409, silently discarding
#: the legal address, registration date and ownership form the user had entered.
_UNDECIDED_CASE_STATUSES = frozenset(
    {
        VerificationCaseStatus.checks_running,
        VerificationCaseStatus.pending_review,
        VerificationCaseStatus.needs_info,
    }
)


def _assert_profile_editable(db: Session, company: Company) -> None:
    """Editable while draft, or while a submitted case is still undecided."""
    if company.status == CompanyStatus.draft:
        return
    if company.status == CompanyStatus.pending_verification:
        undecided = (
            db.query(VerificationCase)
            .filter(
                VerificationCase.company_id == company.id,
                VerificationCase.status.in_(_UNDECIDED_CASE_STATUSES),
            )
            .first()
        )
        if undecided is not None:
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


#: Keys on `logistics_profile` a company may edit once it is already verified.
#:
#: Everything a carrier says about ITSELF for the storefront — the blurb, its
#: reach, what it hauls, its fleet, its pricing model. Deliberately NOT the
#: requisites: nothing here was checked by anyone during verification, so nothing
#: here can be falsified by changing it.
_PUBLIC_LOGISTICS_KEYS = frozenset(
    {
        "city",
        "description",
        "services",
        "from_countries",
        "to_countries",
        "popular_routes",
        "cargo_types",
        "capabilities",
        "tariff_model",
        "years_experience",
        "projects_completed",
        "capability_images",
    }
)

#: Keys on `laboratory_profile` a company may edit once it is already verified.
#:
#: Same bargain as the carrier set: storefront copy about ITSELF, none of which
#: verification checked, so none of which can be falsified by changing it. The
#: contacts (`email`/`phone`) are here too — they are what a lab publishes for
#: people to reach it, not a requisite.
_PUBLIC_LABORATORY_KEYS = frozenset(
    {
        "city",
        "website",
        "email",
        "phone",
        "description",
        "accreditations",
        "methods",
        "years_experience",
        "studies_completed",
        "avg_turnaround_days",
    }
)


def update_public_profile(
    db: Session,
    company: Company,
    account: UserAccount,
    *,
    logistics: dict[str, object] | None = None,
    laboratory: dict[str, object] | None = None,
) -> Company:
    """Patch storefront copy on an ALREADY-VERIFIED company.

    Separate from `update_profile` for one reason, and it is not stylistic:
    `_assert_profile_editable` refuses anything past `draft`/undecided-case, while
    `directory_service._base_query` requires `verified` to appear in a public
    directory at all. Every carrier and laboratory whose page this copy renders on
    is therefore in the exact state where `update_profile` rejects the edit — the
    marketing fields would have been writable only before verification and never
    again.

    Both halves are optional and independent: a company patches the blob for the
    role it actually holds, and passing neither is a no-op rather than a wipe.

    So this skips that gate ON PURPOSE, and narrows what it can reach instead:
    only `_PUBLIC_LOGISTICS_KEYS` / `_PUBLIC_LABORATORY_KEYS`, never a requisite.
    `legal_name`,
    `legal_address` and `registration_date` were checked by a human and stay
    behind `update_profile`; relaxing the gate itself would have unfrozen them
    too. Authorisation is the router's `require_company_admin`.

    Merges rather than replaces, because both profile columns are plain
    `mapped_column(JSONB)` — not `MutableDict.as_mutable` — so SQLAlchemy sees no
    in-place key assignment, and a whole-blob `setattr` (what `update_profile`
    does) would silently drop the `services`/`cargo_types` (or the lab's
    `licenses`) the wizard collected.
    """
    changed: list[str] = []

    def _merge(
        current: object, patch: dict[str, object], allowed: frozenset[str]
    ) -> dict[str, object] | None:
        """The merged blob, or None when the patch moved nothing.

        None rather than the unchanged dict so the caller can skip the assignment
        entirely: `company.laboratory_profile = <equal dict>` still marks the
        attribute dirty, and a no-op PATCH would emit an UPDATE with no audit row
        beside it to explain it.
        """
        merged: dict[str, object] = dict(current) if isinstance(current, dict) else {}
        touched = False
        for key, value in patch.items():
            if key not in allowed:
                continue
            if merged.get(key) != value:
                merged[key] = value
                changed.append(key)
                touched = True
        return merged if touched else None

    # A NEW dict, assigned — see the note above on why mutating one in place would
    # not have been persisted.
    if logistics is not None:
        merged_logistics = _merge(
            company.logistics_profile, logistics, _PUBLIC_LOGISTICS_KEYS
        )
        if merged_logistics is not None:
            company.logistics_profile = merged_logistics
    if laboratory is not None:
        merged_laboratory = _merge(
            company.laboratory_profile, laboratory, _PUBLIC_LABORATORY_KEYS
        )
        if merged_laboratory is not None:
            company.laboratory_profile = merged_laboratory

    if not changed:
        return company

    db.flush()
    event_service.emit(
        db, event_types.COMPANY_PROFILE_UPDATED, "company", company.id,
        {"account_id": account.id, "fields": sorted(changed), "scope": "public_profile"},
    )
    audit_service.write_audit(
        db, None, "company.update_public_profile", "companies", str(company.id),
        {"account_id": account.id, "fields": sorted(changed)},
    )
    return company


def assert_single_account_type(roles: list[CompanyBusinessRoleEnum]) -> None:
    """Raise InvalidBusinessRoles unless `roles` fit exactly one ACCOUNT_TYPES card.

    Empty is allowed (clear roles). Unknown roles (e.g. insurance_provider) and
    mixes across cards (manufacturer+trader, importer+distributor) are rejected.
    """
    role_set = frozenset(roles)
    if not role_set:
        return
    matches = [allowed for allowed in ACCOUNT_TYPE_ROLE_SETS if role_set <= allowed]
    if len(matches) != 1:
        raise InvalidBusinessRoles(
            "roles must belong to a single account type "
            "(buyer / distributor-trader / manufacturer / logistics / laboratory)"
        )


def set_business_roles(
    db: Session, company: Company, roles: list[CompanyBusinessRoleEnum]
) -> list[CompanyBusinessRole]:
    """Replace the company's declared business roles with `roles` (deduped).

    Enforces account-type exclusivity — see `assert_single_account_type`.

    A verified company's roles land as `confirmed` directly (verification already
    vouched for the company; replace-then-declare would silently strip the
    confirmation this endpoint's rows carried). `confirmed_by` stays NULL — this
    is the portal path, there is no staff actor.
    """
    deduped = list(dict.fromkeys(roles))
    assert_single_account_type(deduped)

    status = (
        BusinessRoleStatus.confirmed
        if company.status == CompanyStatus.verified
        else BusinessRoleStatus.declared
    )

    for existing in list(company.business_roles):
        db.delete(existing)
    db.flush()

    created: list[CompanyBusinessRole] = []
    for role in deduped:
        row = CompanyBusinessRole(company_id=company.id, role=role, status=status)
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


#: Roles allowed to change company-wide settings such as branding (FR-M1).
COMPANY_ADMIN_ROLES: frozenset[CompanyMemberRole] = frozenset(
    {CompanyMemberRole.owner, CompanyMemberRole.manager}
)


def require_company_role(
    db: Session,
    account: UserAccount,
    company_id: int,
    allowed: frozenset[CompanyMemberRole],
) -> None:
    """Raise InsufficientCompanyRole unless `account`'s active role is in `allowed`.

    Membership itself is checked separately (`get_company_for`, which 404s for
    outsiders so company existence never leaks). This is the second, narrower gate:
    the caller is a member, but not every member may act. Keep that order — checking
    the role first would turn a non-member's 404 into a 403 and leak existence.
    """
    member = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
        .first()
    )
    if member is None or member.member_role not in allowed:
        raise InsufficientCompanyRole(str(company_id))


def active_business_roles(company: Company) -> frozenset[CompanyBusinessRoleEnum]:
    """Non-revoked (declared OR confirmed) roles — what the company registered as."""
    return frozenset(
        r.role for r in company.business_roles if r.status != BusinessRoleStatus.revoked
    )


def require_business_role(
    company: Company, allowed: frozenset[CompanyBusinessRoleEnum]
) -> None:
    """Raise RoleNotAllowed unless the company's account type permits this flow.

    Same layering as require_company_role: membership (404) is the caller's job
    and comes first, so a non-member never sees this 403. A company holding no
    gateable roles at all (legacy rows, insurance_provider) counts as a buyer —
    fail OPEN to the fullest non-seller view rather than locking a real customer
    out of everything.
    """
    held = active_business_roles(company) & GATEABLE_ROLES
    effective = held or frozenset({CompanyBusinessRoleEnum.importer})
    if not (effective & allowed):
        raise RoleNotAllowed(str(company.id))


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
