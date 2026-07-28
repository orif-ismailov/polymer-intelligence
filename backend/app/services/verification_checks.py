"""Pure verification-check functions (R1 W4 — T4.2).

Each returns a `CheckResult(status, result)` computed from already-loaded data —
no DB, no network. The task layer (`app/tasks/verification.py`) persists the result
onto the `verification_checks` row and the evaluator decides the case from the set
of results. Keeping these pure makes the check matrix trivially unit-testable and
replayable.

R1 ships four checks: tax-id format, bank requisites, documents complete, and
manual KYB (a human item that stays `pending` until staff resolve it). R3 added
the E-IMZO check; **P7.c adds the two registry checks**, which are the first that
can legitimately be `unavailable` — there is no realtime state-registry API for
private companies without ПЦД access.

The registry checks read a `registry_snapshots` row and nothing else, on purpose:
the same code then judges a ПЦД answer and an operator's transcription of
my.soliq.uz. The difference between those two lives in the snapshot's `source`
column, which is where it belongs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.core.crypto import decrypt_pii
from app.integrations import gov_registry
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


# ── Registry checks (P7.c) ────────────────────────────────────────────────────


class _HasPayload(Protocol):
    """A `RegistrySnapshot`, reduced to the one attribute these checks read.

    Structural typing keeps the functions genuinely pure — they need no ORM row,
    so a test can hand them a dict-holder and a future channel can hand them
    something else entirely.
    """

    @property
    def payload(self) -> dict[str, object]: ...


#: Legal-form markers stripped before comparing organisation names. Every source
#: writes these differently, and none of them identifies the company.
_LEGAL_FORMS = (
    "ооо", "оао", "зао", "ао", "чп", "мчж", "ак", "уп",
    "mchj", "ooo", "ajq", "oao", "aj", "llc", "jsc", "ltd", "lc", "inc", "co",
)

_PUNCT_RE = re.compile(r"[^0-9a-zа-яё\s]", flags=re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def normalize_org_name(name: str | None) -> str:
    """Comparable form of an organisation name.

    Drops quotes/punctuation, the legal-form marker and casing, and collapses
    whitespace — the differences that are guaranteed noise between a registry
    extract and our own record. Transliteration is deliberately NOT applied:
    Cyrillic and Latin spellings are a real difference worth a human's glance,
    and a transliteration table that silently equates them would hide the case
    where two genuinely different companies share a romanisation.
    """
    if not name:
        return ""
    folded = unicodedata.normalize("NFKC", name).casefold()
    cleaned = _WS_RE.sub(" ", _PUNCT_RE.sub(" ", folded)).strip()
    words = [w for w in cleaned.split(" ") if w and w not in _LEGAL_FORMS]
    return " ".join(words)


def check_gov_registry(company: Company, snapshot: _HasPayload | None) -> CheckResult:
    """Judge a company against its newest state-registry snapshot.

    `unavailable` when there is no snapshot: we have no registry channel yet, and
    that is a fact about US. Turning it into a `failed` check would manufacture a
    finding about a real business and — because a failed automated check sends the
    case to `needs_info` — ask the company to fix our integration.
    """
    if snapshot is None:
        return CheckResult(
            VerificationCheckStatus.unavailable,
            {"reason": "no_snapshot", "note": "no registry channel and no manual check yet"},
        )

    record = gov_registry.company_from_payload(dict(snapshot.payload))
    payload: dict[str, object] = {
        "registry_status": record.status,
        "raw_status": record.raw_status,
        "registry_name": record.name,
        "registry_inn": record.inn,
        "director": record.director,
    }

    # Either the wrong company was looked up, or the registry disagrees about the
    # tax id. Both are hard stops.
    if record.inn and company.tax_id and record.inn != company.tax_id:
        payload["reason"] = "inn_mismatch"
        return CheckResult(VerificationCheckStatus.failed, payload)

    if record.status in {gov_registry.COMPANY_LIQUIDATED, gov_registry.COMPANY_SUSPENDED}:
        return CheckResult(VerificationCheckStatus.failed, payload)

    if record.status != gov_registry.COMPANY_ACTIVE:
        # The registry answered but stated no status. Not a pass — a human looks.
        payload["reason"] = "status_unknown"
        return CheckResult(VerificationCheckStatus.warning, payload)

    ours = normalize_org_name(company.legal_name)
    theirs = normalize_org_name(record.name)
    if ours and theirs and ours != theirs:
        # The registry is authoritative, but our record may be a trading name or
        # a different romanisation. Compare, do not reject.
        payload["name_matches"] = False
        return CheckResult(VerificationCheckStatus.warning, payload)

    payload["name_matches"] = True
    return CheckResult(VerificationCheckStatus.passed, payload)


def check_vat_status(company: Company, snapshot: _HasPayload | None) -> CheckResult:
    """Judge a company's VAT-register standing.

    **Not being a VAT payer is a WARNING, not a failure.** Not every Uzbek company
    is obliged to register for VAT, so refusing verification on that ground would
    be legally wrong. The warning exists because a counterparty's VAT status
    changes what an invoice between them looks like, which staff should see.
    """
    if snapshot is None:
        return CheckResult(
            VerificationCheckStatus.unavailable,
            {"reason": "no_snapshot", "note": "VAT register not checked yet"},
        )

    record = gov_registry.vat_from_payload(dict(snapshot.payload))
    payload: dict[str, object] = {
        "registered": record.registered,
        "certificate_no": record.certificate_no,
        "raw_status": record.raw_status,
    }
    status = (
        VerificationCheckStatus.passed
        if record.registered
        else VerificationCheckStatus.warning
    )
    return CheckResult(status, payload)
