"""Pure verification-check functions (R1 W4 — T4.2).

Each returns a `CheckResult(status, result)` computed from already-loaded data —
no DB, no network. The task layer (`app/tasks/verification.py`) persists the result
onto the `verification_checks` row and the evaluator decides the case from the set
of results. Keeping these pure makes the check matrix trivially unit-testable and
replayable.

R1 ships four checks: tax-id format, bank requisites, documents complete, and
manual KYB (a human item that stays `pending` until staff resolve it). P2/R3 add
gov-registry / e-invoice / E-IMZO checks that CAN be `unavailable` (retry path).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.crypto import decrypt_pii
from app.models.companies import Company, CompanyBankAccount
from app.models.enums import (
    CompanyBusinessRole,
    DocumentReviewStatus,
    VerificationCheckStatus,
    VerificationDocumentKind,
)
from app.models.verification import VerificationDocument


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check: a status + a JSON-serialisable findings payload."""

    status: VerificationCheckStatus
    result: dict[str, object]


# Regulated business roles that require an extra document (R1 rules).
_ROLE_REQUIRED_DOCS: dict[CompanyBusinessRole, VerificationDocumentKind] = {
    CompanyBusinessRole.insurance_provider: VerificationDocumentKind.license,
    CompanyBusinessRole.laboratory: VerificationDocumentKind.certificate,
}


def check_tax_id_format(company: Company) -> CheckResult:
    """UZ STIR = 9 digits; other jurisdictions just require a non-empty tax id."""
    tax_id = (company.tax_id or "").strip()
    ok = (
        (tax_id.isdigit() and len(tax_id) == 9)
        if company.jurisdiction == "UZ"
        else bool(tax_id)
    )
    return CheckResult(
        VerificationCheckStatus.passed if ok else VerificationCheckStatus.failed,
        {"jurisdiction": company.jurisdiction, "digits": len(tax_id), "valid": ok},
    )


def check_bank_requisites(
    company: Company, accounts: list[CompanyBankAccount]
) -> CheckResult:
    """No account → warning; else every account must have a 5-digit MFO + 20-digit number.

    The account number is decrypted only to validate its length; it is NEVER put in
    the result payload (only the masked last4 identifies a problem account).
    """
    if not accounts:
        return CheckResult(VerificationCheckStatus.warning, {"reason": "no_bank_account"})

    problems: list[dict[str, str]] = []
    for account in accounts:
        if not (account.bank_mfo.isdigit() and len(account.bank_mfo) == 5):
            problems.append({"last4": account.account_last4, "issue": "bad_mfo"})
        try:
            number = decrypt_pii(account.account_number_enc)
        except Exception:  # noqa: BLE001 — treat undecryptable ciphertext as a problem
            problems.append({"last4": account.account_last4, "issue": "undecryptable"})
            continue
        if not (number.isdigit() and len(number) == 20):
            problems.append({"last4": account.account_last4, "issue": "bad_account_length"})

    status = VerificationCheckStatus.failed if problems else VerificationCheckStatus.passed
    return CheckResult(status, {"accounts": len(accounts), "problems": problems})


def check_documents_complete(
    company: Company,
    documents: Iterable[VerificationDocument],
    declared_roles: Iterable[CompanyBusinessRole],
    *,
    has_bank_account: bool,
    eimzo_passed: bool = False,
) -> CheckResult:
    """registration_certificate required (UNLESS an E-IMZO signature supersedes it,
    R3 TA1.5); bank_letter iff a bank account exists; plus per-role docs for
    regulated roles. Missing kinds → failed with the list.
    """
    present = {
        doc.kind
        for doc in documents
        if doc.status != DocumentReviewStatus.rejected
    }

    required: set[VerificationDocumentKind] = set()
    # A verified E-IMZO signature carries the registry-certified org identity, so it
    # supersedes the uploaded registration certificate (bank_letter rule unchanged).
    if not eimzo_passed:
        required.add(VerificationDocumentKind.registration_certificate)
    if has_bank_account:
        required.add(VerificationDocumentKind.bank_letter)
    for role in declared_roles:
        extra = _ROLE_REQUIRED_DOCS.get(role)
        if extra is not None:
            required.add(extra)

    missing = sorted(kind.value for kind in required - present)
    payload: dict[str, object] = {
        "required": sorted(kind.value for kind in required),
        "missing": missing,
        "eimzo_passed": eimzo_passed,
    }
    status = (
        VerificationCheckStatus.failed if missing else VerificationCheckStatus.passed
    )
    return CheckResult(status, payload)


def check_manual_kyb() -> CheckResult:
    """Human KYB item — always starts pending; staff resolve it (approve/waive)."""
    return CheckResult(VerificationCheckStatus.pending, {"note": "awaiting_human_review"})
