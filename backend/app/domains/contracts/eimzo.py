"""E-IMZO identity confirmation service (R3 Stage A — TA1.4/TA1.5).

Two entry points:

* ``issue_challenge`` mints a single-use, short-TTL nonce in Redis for a given
  (company, account) and returns it for the browser to sign.
* ``verify`` consumes the challenge, confirms the signer through Didox, and — on a
  valid signature whose certificate INN matches the company — fills+locks the
  company requisites, stores immutable evidence + encrypted person data (§6.2),
  records the ``eimzo_signature`` check as ``passed`` (confidence
  ``method: didox``), auto-confirms the signer as owner, and re-runs the case
  evaluator (so with ``verification_auto_approve`` on and the other automated checks
  green — the reg-cert requirement now relaxed, TA1.5 — the case approves with no
  staff touch).

**Verification moved off the UNICON sidecar** (see ``domains/edi/identity``). That
sidecar is licensed, was never obtained and runs nowhere, so this whole flow
answered 503 outside a dev stack. Didox refuses a signature that does not verify
for the given INN, which is the same statement, from a provider we already hold a
token for — and minting the session here spares the user a second key password
later on the 007 document rail.

**What the challenge still is, and no longer is.** It is minted, stored per
(company, account) and consumed exactly once, so a verify cannot be replayed
against US. It is NOT covered by the signature any more: the browser now signs the
company's INN, because that is what Didox authenticates. Nothing in the envelope
proves when it was made, so the single-use nonce is the whole of our freshness
guarantee rather than a second belt beside the sidecar's. Do not describe it in a
comment as "the signed challenge" — it is not one.

Degradation (ARCHITECTURE invariant): a provider outage surfaces as
``ProviderUnavailable`` (→ 503) and never blocks the manual path. A signature Didox
refuses records a ``failed`` check with a reason rather than raising — the split
that keeps a forged signature from being waved through as an outage. A company with
no Didox account raises ``DidoxAccountRequired`` (→ 409) and records nothing: the
signature was never judged, and a failed check there would libel an honest
applicant. PINFL/full name are never returned or logged — only a masked
``****{last4}``.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company, CompanyMember
from app.domains.contracts.eimzo_models import SignatureEvidence
from app.domains.edi.identity import (
    DidoxIdentityResult,
    DidoxSigner,
    remember_signer,
    signer_changed,
    verify_identity,
)
from app.domains.verification import service as verification_service
from app.domains.verification.models import VerificationCase, VerificationCheck
from app.models.enums import (
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyStatus,
    VerificationCaseStatus,
    VerificationCaseType,
    VerificationCheckStatus,
    VerificationCheckType,
)
from app.services import (
    audit_service,
    event_service,
    event_types,
    storage_service,
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
    #: None only for a verified company that has never had a case at all.
    case: VerificationCase | None
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
    case = verification_service.open_case_for(db, company.id)
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


def _registry_requisites(
    db: Session, tax_id: str | None, redis_client: redis.Redis[str] | None
) -> tuple[str | None, str | None]:
    """The registry's `(legal_name, director)` for this STIR, or `(None, None)`.

    **Nothing here may fail a signature that already verified.** By the time this
    runs the sidecar has accepted the PKCS#7 and the evidence is in S3, so an
    exception would 500 a legally completed signing over a display string. Hence
    the bare `Exception`: `lookup_company` documents `CompanyNotFound` and
    `ProviderUnavailable`, but it reaches an HTTP client through two adapters and
    an unexpected fault there must degrade to "the certificate wins", which is
    exactly the behaviour this whole path used to have unconditionally.
    """
    if not tax_id:
        return None, None
    from app.domains.companies.lookup import lookup_company  # noqa: PLC0415 — avoids a cycle

    try:
        info = lookup_company(db, tax_id, redis_client=redis_client)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.info("eimzo.registry_requisites_unavailable", extra={"error": str(exc)})
        return None, None
    return (info.name or "").strip() or None, (info.director or "").strip() or None


def _apply_identity(
    db: Session,
    company: Company,
    signer: DidoxSigner,
    redis_client: redis.Redis[str] | None = None,
) -> None:
    """Fill + lock the company's displayed requisites (reject later PATCH).

    The certificate FREEZES these fields; it does not necessarily supply them.
    Both sources carry a name and a director, they disagree, and the registry is
    the better one on every axis that matters here: E-IMZO v6.4.7 reports the
    subject DN **lowercased**, and a certificate is a snapshot taken at issuance
    that can be a year stale, while `/v1/utils/info/{tin}` is current and
    correctly cased. Signing with a real key used to overwrite
    «"IMEX INDUSTRIAL GROUP CA" MAS'ULIYATI CHEKLANGAN JAMIYAT» with
    «dev_imex industrial group ca mchj» and then lock it.

    The identity guarantee is untouched: it rests on `org_inn == company.tax_id`,
    checked in `verify` before anything is written, and the certificate subject is
    kept verbatim on `signature_evidence.cert_subject` either way. The signer's own
    name and PINFL live on the encrypted `CompanyPersonData` row, so preferring the
    REGISTERED director here loses nothing — the two answer different questions.
    """
    registry_name, registry_director = _registry_requisites(db, company.tax_id, redis_client)
    name = registry_name or signer.org_name
    director = registry_director or signer.full_name
    if name:
        company.legal_name = name
    if director:
        company.director_name = director
    company.identity_locked = True
    db.flush()


def _store_evidence(
    db: Session,
    company: Company,
    account: UserAccount,
    challenge: str,
    pkcs7_b64: str,
    result: DidoxIdentityResult,
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
        # NOTE: full name / PINFL are NOT copied here in the clear.
        #
        # `serial_number` used to sit here and is GONE rather than None: the
        # sidecar read it off the certificate, and Didox's profile does not carry
        # it. Rows written before this change keep theirs — a key absent from new
        # evidence says "never established", which a null would blur into "the
        # certificate had none".
    }
    evidence = SignatureEvidence(
        company_id=company.id,
        user_account_id=account.id,
        purpose=_PURPOSE_IDENTITY,
        challenge=challenge,
        pkcs7_storage_path=path,
        pkcs7_sha256=sha,
        cert_subject=cert_subject,
        # When the signature was made — NOT result.cert_valid_from (that is the
        # certificate's issuance/validity start, often years earlier, and would
        # misdate the evidence). Mirrors contract_service's signing stamp.
        signed_at=company_service.now_utc(),
    )
    db.add(evidence)
    db.flush()
    return evidence


def _store_person_data(
    db: Session, company: Company, account: UserAccount, signer: DidoxSigner
) -> None:
    remember_signer(db, company.id, account.id, signer, position=signer.position)


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
    signature_hex: str,
) -> EimzoVerifyOutcome:
    """Consume the challenge, confirm the signer, apply identity effects.

    `signature_hex` is the raw signature inside the PKCS#7, which the module has
    always returned and we never read. It is required, not optional: Didox's
    `/v1/dsvs/timestamp` takes both halves and refuses a bare envelope, so a
    caller that omits it cannot be served at all — better a 422 from the schema
    than a provider rejection three calls later.

    Raises: ChallengeExpired, CertCompanyMismatch, company_service.CompanyAlreadyRegistered,
    edi.identity.DidoxAccountRequired, and (propagated) ProviderUnavailable.
    """
    challenge = _pop_challenge(redis_client, company.id, account.id)
    if challenge is None:
        raise ChallengeExpired(str(company.id))

    # Single-use on OUR side only — the signature covers the INN, not this nonce.
    result = verify_identity(
        redis_client, company, pkcs7_64=pkcs7_b64, signature_hex=signature_hex
    )  # ProviderUnavailable propagates → 503

    if (
        company.status == CompanyStatus.verified
        and verification_service.open_case_for(db, company.id) is None
    ):
        quiet = _reconfirm_verified(db, redis_client, company, account, challenge, pkcs7_b64, result)
        if quiet is not None:
            return quiet

    case = _open_or_create_case(db, company)
    _spawn_missing_checks(db, case.id)

    if not result.ok:
        return _record_failure(db, case, result)

    signer = result.signer or DidoxSigner()

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
    _apply_identity(db, company, signer, redis_client)
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

    # Record the eimzo_signature check. `method` is the only record of WHO judged
    # the signature, so it moved with the rail: `eimzo` means the UNICON sidecar
    # checked the envelope, `didox` means the operator accepted it as auth for
    # this INN. Old rows keep `eimzo` and stay true about themselves.
    holder_masked = _mask_pinfl(signer.pinfl)
    eimzo_check = _get_check(db, case.id, VerificationCheckType.eimzo_signature)
    now = company_service.now_utc()
    if eimzo_check is not None:
        eimzo_check.status = VerificationCheckStatus.passed
        eimzo_check.finished_at = now
        eimzo_check.result = {
            "method": "didox",
            "org_inn": _mask_inn(signer.org_inn),
            "holder": holder_masked,
            "holder_name": signer.full_name,  # org director (shown to own members)
            "position": signer.position,
            # `serial` is gone with the sidecar that read it — see _store_evidence.
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


def _latest_case(db: Session, company_id: int) -> VerificationCase | None:
    return (
        db.query(VerificationCase)
        .filter(VerificationCase.company_id == company_id)
        .order_by(VerificationCase.id.desc())
        .first()
    )


def _reconfirm_verified(
    db: Session,
    redis_client: redis.Redis[str],
    company: Company,
    account: UserAccount,
    challenge: str,
    pkcs7_b64: str,
    result: DidoxIdentityResult,
) -> EimzoVerifyOutcome | None:
    """A company staff already verified signs its ИНН again — usually to unblock
    a Didox document, which needs the signer on file.

    Nothing here is for a person to review: the same ИНН, the same key, and the
    director the registry already named. So it is recorded — evidence, signer,
    audit — and the company's existing case stays the answer. It used to open a
    «точечная проверка» with a pending manual KYB, which put every such company
    in /verification twice and in front of staff for nothing.

    Returns None — «handle it as a case» — when someone OTHER than the person on
    file is now signing: a change of director is exactly what staff should see.
    """
    latest = _latest_case(db, company.id)
    if not result.ok:
        reason = result.error or "signature_invalid"
        audit_service.write_audit(
            db, None, "company.eimzo_verify_failed", "companies", str(company.id),
            {"account_id": account.id, "reason": reason, "reconfirm": True},
        )
        db.flush()
        return EimzoVerifyOutcome(ok=False, case=latest, reason=reason)

    signer = result.signer or DidoxSigner()
    if company.tax_id and signer.org_inn and signer.org_inn != company.tax_id:
        raise CertCompanyMismatch(_mask_inn(signer.org_inn), _mask_inn(company.tax_id))
    if signer_changed(db, company.id, signer):
        return None

    _store_evidence(db, company, account, challenge, pkcs7_b64, result)
    _store_person_data(db, company, account, signer)
    _apply_identity(db, company, signer, redis_client)
    _confirm_owner(db, company, account)
    audit_service.write_audit(
        db, None, "company.eimzo_reconfirm", "companies", str(company.id),
        {"account_id": account.id, "org_inn": _mask_inn(signer.org_inn)},
    )
    db.flush()
    return EimzoVerifyOutcome(
        ok=True, case=latest, holder_masked=_mask_pinfl(signer.pinfl)
    )


def _record_failure(
    db: Session, case: VerificationCase, result: DidoxIdentityResult
) -> EimzoVerifyOutcome:
    """Record eimzo_signature=failed with a reason (invalid/revoked signature)."""
    reason = result.error or "signature_invalid"
    check = _get_check(db, case.id, VerificationCheckType.eimzo_signature)
    if check is not None:
        check.status = VerificationCheckStatus.failed
        check.finished_at = company_service.now_utc()
        check.result = {"method": "didox", "reason": reason}
    audit_service.write_audit(
        db, None, "company.eimzo_verify_failed", "companies", str(case.company_id),
        {"case_id": case.id, "reason": reason},
    )
    db.flush()
    return EimzoVerifyOutcome(ok=False, case=case, reason=reason)
