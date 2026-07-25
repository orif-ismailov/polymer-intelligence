"""E-IMZO identity confirmation service (R3 Stage A — TA1.4/TA1.5).

Two entry points:

* ``issue_challenge`` mints a single-use, short-TTL nonce in Redis for a given
  (company, account) and returns it for the browser to sign.
* ``verify`` consumes the challenge, verifies the PKCS#7 through the gateway
  adapter, and — on a valid signature whose certificate INN matches the company —
  fills+locks the company requisites, stores immutable evidence + encrypted person
  data (§6.2), records the ``eimzo_signature`` check as ``passed`` (confidence
  ``method: eimzo``), auto-confirms the signer as owner, and re-runs the case
  evaluator (so with ``verification_auto_approve`` on and the other automated checks
  green — the reg-cert requirement now relaxed, TA1.5 — the case approves with no
  staff touch).

Degradation (ARCHITECTURE invariant): a sidecar outage surfaces as
``ProviderUnavailable`` (→ 503) and never blocks the manual path. An invalid /
revoked signature records a ``failed`` check with a reason rather than raising.
PINFL/full name are never returned or logged — only a masked ``****{last4}``.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import encrypt_pii
from app.integrations.eimzo import EimzoSigner, EimzoVerifyResult, verify_pkcs7
from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyMember
from app.models.eimzo import CompanyPersonData, SignatureEvidence
from app.models.enums import (
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyStatus,
    VerificationCaseStatus,
    VerificationCaseType,
    VerificationCheckStatus,
    VerificationCheckType,
)
from app.models.verification import VerificationCase, VerificationCheck
from app.services import (
    audit_service,
    company_service,
    event_service,
    event_types,
    storage_service,
    verification_service,
)

logger = logging.getLogger(__name__)

_PURPOSE_IDENTITY = "company_identity"

# Automated R1 checks re-run synchronously alongside an E-IMZO confirmation so the
# case can be evaluated immediately (manual_kyb is a human item, eimzo_signature is
# set directly to passed — neither is run here).
_SYNC_CHECK_TYPES: tuple[VerificationCheckType, ...] = (
    VerificationCheckType.tax_id_format,
    VerificationCheckType.bank_requisites,
    VerificationCheckType.documents_complete,
)
_ALL_SPAWN_TYPES: tuple[VerificationCheckType, ...] = (
    VerificationCheckType.tax_id_format,
    VerificationCheckType.bank_requisites,
    VerificationCheckType.documents_complete,
    VerificationCheckType.manual_kyb,
    VerificationCheckType.eimzo_signature,
)


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class ChallengeExpired(Exception):
    """No live challenge for this (company, account) — missing, expired, or replayed."""


class CertCompanyMismatch(Exception):
    """The certificate's organisation INN does not match the company tax_id."""

    def __init__(self, cert_inn_masked: str, company_inn_masked: str) -> None:
        super().__init__("cert/company INN mismatch")
        self.cert_inn_masked = cert_inn_masked
        self.company_inn_masked = company_inn_masked


@dataclass(frozen=True)
class EimzoVerifyOutcome:
    """Result of a verify() call for the API layer."""

    ok: bool
    case: VerificationCase
    reason: str | None = None
    holder_masked: str | None = None


# ── Masking helpers (PINFL/INN never surfaced in the clear) ───────────────────


def _mask_pinfl(pinfl: str | None) -> str | None:
    if not pinfl:
        return None
    return f"****{pinfl[-4:]}"


def _mask_inn(inn: str | None) -> str:
    if not inn:
        return "****"
    if len(inn) <= 4:
        return "****"
    return f"{inn[:2]}****{inn[-2:]}"


# ── Challenge lifecycle (Redis, single-use) ───────────────────────────────────


def _challenge_key(company_id: int, account_id: int) -> str:
    return f"eimzo:ch:{company_id}:{account_id}"


def issue_challenge(
    redis_client: redis.Redis[str], company_id: int, account_id: int
) -> str:
    """Mint + store a single-use challenge (TTL = EIMZO_CHALLENGE_TTL_SECONDS)."""
    challenge = secrets.token_urlsafe(32)
    redis_client.setex(
        _challenge_key(company_id, account_id),
        settings.EIMZO_CHALLENGE_TTL_SECONDS,
        challenge,
    )
    return challenge


def _pop_challenge(
    redis_client: redis.Redis[str], company_id: int, account_id: int
) -> str | None:
    """Atomically fetch+delete the challenge (single-use); None if absent/expired."""
    key = _challenge_key(company_id, account_id)
    value = redis_client.getdel(key)
    return value if isinstance(value, str) else None


# ── Case / check helpers ──────────────────────────────────────────────────────


def _open_or_create_case(db: Session, company: Company) -> VerificationCase:
    case = verification_service._open_case_for(db, company.id)
    if case is not None:
        return case
    # No open case (e.g. a verified company re-confirming) → a targeted case.
    case = VerificationCase(
        company_id=company.id,
        case_type=VerificationCaseType.targeted,
        status=VerificationCaseStatus.draft,
    )
    db.add(case)
    db.flush()
    return case


def _existing_check_types(db: Session, case_id: int) -> set[VerificationCheckType]:
    return {
        c.check_type
        for c in db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all()
    }


def _spawn_missing_checks(db: Session, case_id: int) -> None:
    present = _existing_check_types(db, case_id)
    for check_type in _ALL_SPAWN_TYPES:
        if check_type not in present:
            db.add(
                VerificationCheck(
                    case_id=case_id,
                    check_type=check_type,
                    status=VerificationCheckStatus.pending,
                )
            )
    db.flush()


def _get_check(db: Session, case_id: int, check_type: VerificationCheckType) -> VerificationCheck | None:
    return (
        db.query(VerificationCheck)
        .filter(
            VerificationCheck.case_id == case_id,
            VerificationCheck.check_type == check_type,
        )
        .first()
    )


def _run_sync_checks(db: Session, case: VerificationCase) -> None:
    """Compute + persist the automated R1 checks in-process (no verify queue)."""
    from app.tasks.verification import _run_check  # noqa: PLC0415 — task-layer glue

    now = company_service.now_utc()
    for check_type in _SYNC_CHECK_TYPES:
        check = _get_check(db, case.id, check_type)
        if check is None:
            continue
        result = _run_check(db, check)
        check.status = result.status
        check.result = result.result
        check.finished_at = now
    db.flush()


# ── Identity + evidence application ───────────────────────────────────────────


def _apply_identity(db: Session, company: Company, signer: EimzoSigner) -> None:
    """Fill + lock the certificate-carried requisites (reject later PATCH)."""
    if signer.org_name:
        company.legal_name = signer.org_name
    if signer.full_name:
        company.director_name = signer.full_name
    company.identity_locked = True
    db.flush()


def _store_evidence(
    db: Session,
    company: Company,
    account: UserAccount,
    challenge: str,
    pkcs7_b64: str,
    result: EimzoVerifyResult,
) -> SignatureEvidence:
    import base64  # noqa: PLC0415

    try:
        pkcs7_bytes = base64.b64decode(pkcs7_b64)
    except (ValueError, TypeError):
        pkcs7_bytes = pkcs7_b64.encode("utf-8")
    path, sha = storage_service.store_eimzo_pkcs7(company.id, pkcs7_bytes)
    signer = result.signer
    cert_subject = {
        "org_name": signer.org_name if signer else None,
        "org_inn": signer.org_inn if signer else None,
        "position": signer.position if signer else None,
        "serial_number": signer.serial_number if signer else None,
        # NOTE: full name / PINFL are NOT copied here in the clear.
    }
    evidence = SignatureEvidence(
        company_id=company.id,
        user_account_id=account.id,
        purpose=_PURPOSE_IDENTITY,
        challenge=challenge,
        pkcs7_storage_path=path,
        pkcs7_sha256=sha,
        cert_subject=cert_subject,
        signed_at=result.cert_valid_from,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _store_person_data(
    db: Session, company: Company, account: UserAccount, signer: EimzoSigner
) -> None:
    if not (signer.full_name or signer.pinfl):
        return
    db.add(
        CompanyPersonData(
            company_id=company.id,
            user_account_id=account.id,
            full_name_enc=encrypt_pii(signer.full_name or ""),
            pinfl_enc=encrypt_pii(signer.pinfl or ""),
            pinfl_last4=(signer.pinfl or "")[-4:] or None,
            position=signer.position,
            source="eimzo",
        )
    )
    db.flush()


def _confirm_owner(db: Session, company: Company, account: UserAccount) -> None:
    """Auto-confirm the signer's membership as owner (create if absent)."""
    member = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_account_id == account.id,
        )
        .first()
    )
    if member is None:
        db.add(
            CompanyMember(
                company_id=company.id,
                user_account_id=account.id,
                member_role=CompanyMemberRole.owner,
                status=CompanyMemberStatus.active,
            )
        )
    else:
        member.member_role = CompanyMemberRole.owner
        member.status = CompanyMemberStatus.active
    db.flush()


def _adopt_tax_id(db: Session, company: Company, cert_inn: str) -> None:
    existing = (
        db.query(Company)
        .filter(
            Company.jurisdiction == company.jurisdiction,
            Company.tax_id == cert_inn,
            Company.id != company.id,
        )
        .first()
    )
    if existing is not None:
        raise company_service.CompanyAlreadyRegistered(f"{company.jurisdiction}/{cert_inn}")
    company.tax_id = cert_inn
    db.flush()


# ── Verify ────────────────────────────────────────────────────────────────────


def verify(
    db: Session,
    redis_client: redis.Redis[str],
    company: Company,
    account: UserAccount,
    pkcs7_b64: str,
) -> EimzoVerifyOutcome:
    """Consume the challenge, verify the signature, apply identity effects.

    Raises: ChallengeExpired, CertCompanyMismatch, company_service.CompanyAlreadyRegistered,
    and (propagated) integrations.eimzo.ProviderUnavailable.
    """
    challenge = _pop_challenge(redis_client, company.id, account.id)
    if challenge is None:
        raise ChallengeExpired(str(company.id))

    result = verify_pkcs7(pkcs7_b64, challenge)  # ProviderUnavailable propagates → 503

    case = _open_or_create_case(db, company)
    _spawn_missing_checks(db, case.id)

    if not result.ok:
        return _record_failure(db, case, result)

    signer = result.signer or EimzoSigner()

    # INN match rule (both values masked in the error).
    cert_inn = signer.org_inn
    if company.tax_id and cert_inn and cert_inn != company.tax_id:
        raise CertCompanyMismatch(_mask_inn(cert_inn), _mask_inn(company.tax_id))
    if not company.tax_id and cert_inn:
        _adopt_tax_id(db, company, cert_inn)

    # Persist immutable evidence + encrypted person data.
    _store_evidence(db, company, account, challenge, pkcs7_b64, result)
    _store_person_data(db, company, account, signer)

    # Fill + lock requisites; confirm signer as owner.
    _apply_identity(db, company, signer)
    _confirm_owner(db, company, account)

    # Move the case into an evaluatable state (first-time submit via E-IMZO).
    newly_submitted = case.status in {
        VerificationCaseStatus.draft,
        VerificationCaseStatus.needs_info,
    }
    if newly_submitted:
        case.status = VerificationCaseStatus.checks_running
        case.submitted_at = company_service.now_utc()
        if company.status == CompanyStatus.draft:
            company_service.transition(
                db, company, CompanyStatus.pending_verification, actor={"account_id": account.id}
            )

    # Record the eimzo_signature check (confidence tier: method=eimzo).
    holder_masked = _mask_pinfl(signer.pinfl)
    eimzo_check = _get_check(db, case.id, VerificationCheckType.eimzo_signature)
    now = company_service.now_utc()
    if eimzo_check is not None:
        eimzo_check.status = VerificationCheckStatus.passed
        eimzo_check.finished_at = now
        eimzo_check.result = {
            "method": "eimzo",
            "org_inn": _mask_inn(signer.org_inn),
            "holder": holder_masked,
            "holder_name": signer.full_name,  # org director (shown to own members)
            "position": signer.position,
            "serial": signer.serial_number,
            "signed_at": now.isoformat(),
        }
    db.flush()

    # Now run the other automated checks (reg-cert requirement relaxed by TA1.5).
    _run_sync_checks(db, case)

    if newly_submitted:
        event_service.emit(
            db, event_types.VERIFICATION_CASE_SUBMITTED, "verification_case", case.id,
            {"company_id": company.id, "account_id": account.id, "via": "eimzo"},
        )
    event_service.emit(
        db, event_types.COMPANY_EIMZO_CONFIRMED, "company", company.id,
        {"case_id": case.id, "account_id": account.id},
    )
    event_service.emit(
        db, event_types.VERIFICATION_CHECK_COMPLETED, "verification_check",
        eimzo_check.id if eimzo_check else case.id,
        {"case_id": case.id, "check_status": "passed", "check_type": "eimzo_signature"},
    )
    audit_service.write_audit(
        db, None, "company.eimzo_verify", "companies", str(company.id),
        {"account_id": account.id, "case_id": case.id, "org_inn": _mask_inn(signer.org_inn)},
    )
    db.flush()

    verification_service.on_check_completed(db, case.id)
    db.refresh(case)
    return EimzoVerifyOutcome(ok=True, case=case, holder_masked=holder_masked)


def _record_failure(
    db: Session, case: VerificationCase, result: EimzoVerifyResult
) -> EimzoVerifyOutcome:
    """Record eimzo_signature=failed with a reason (invalid/revoked signature)."""
    reason = result.error or "signature_invalid"
    check = _get_check(db, case.id, VerificationCheckType.eimzo_signature)
    if check is not None:
        check.status = VerificationCheckStatus.failed
        check.finished_at = company_service.now_utc()
        check.result = {"method": "eimzo", "reason": reason}
    audit_service.write_audit(
        db, None, "company.eimzo_verify_failed", "companies", str(case.company_id),
        {"case_id": case.id, "reason": reason},
    )
    db.flush()
    return EimzoVerifyOutcome(ok=False, case=case, reason=reason)
