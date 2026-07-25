"""Contract lifecycle service (R3 Stage B — TB1.2).

State machine (data, per ARCHITECTURE §6):

    draft ─► pending_counterparty ─► pending_signatures ─► active
      │             │                       │
      └─ cancelled  ├─ declined             ├─ declined
                    └─ cancelled            ├─ cancelled
                                            └─ expired (TTL beat)

Both companies must be `verified`. Terms are edited only in `draft` (any edit
re-renders the PDF + sha256). Signatures happen only in `pending_signatures`, via
E-IMZO: the challenge is `contract:{public_id}:{document_sha256}` (single-use in
Redis, bound to the document hash — a re-render invalidates outstanding challenges);
the certificate's org INN must match the signing company's tax_id. Both signatures
present → `active` (taken under a `SELECT … FOR UPDATE` row lock so two concurrent
final signatures activate exactly once).
"""

from __future__ import annotations

import base64
import datetime
import logging

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_pii
from app.integrations.eimzo import verify_pkcs7
from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyBankAccount
from app.models.contracts import Contract, ContractSignature, ContractTemplate
from app.models.eimzo import SignatureEvidence
from app.models.enums import (
    BankAccountStatus,
    CompanyStatus,
    ContractStatus,
)
from app.services import (
    audit_service,
    company_service,
    contract_render,
    event_service,
    event_types,
    storage_service,
)
from app.services.eimzo_service import CertCompanyMismatch

logger = logging.getLogger(__name__)

_PURPOSE_CONTRACT = "contract"

# ── State machine (data) ──────────────────────────────────────────────────────

_TRANSITIONS: dict[ContractStatus, set[ContractStatus]] = {
    ContractStatus.draft: {ContractStatus.pending_counterparty, ContractStatus.cancelled},
    ContractStatus.pending_counterparty: {
        ContractStatus.pending_signatures,
        ContractStatus.declined,
        ContractStatus.cancelled,
    },
    ContractStatus.pending_signatures: {
        ContractStatus.active,
        ContractStatus.declined,
        ContractStatus.cancelled,
        ContractStatus.expired,
    },
    ContractStatus.active: set(),
    ContractStatus.declined: set(),
    ContractStatus.cancelled: set(),
    ContractStatus.expired: set(),
}


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class CompanyNotVerified(Exception):
    """A contract party is not a verified company."""


class VariablesInvalid(Exception):
    """The supplied variables fail the template's schema (missing/invalid fields)."""

    def __init__(self, fields: list[str]) -> None:
        super().__init__("invalid variables")
        self.fields = fields


class InvalidContractTransition(Exception):
    """The requested contract status transition is not allowed."""


class NotAParty(Exception):
    """The company is neither the initiator nor the counterparty of the contract."""


class ContractNotEditable(Exception):
    """Variables can only be edited while the contract is a draft."""


class ChallengeExpired(Exception):
    """No live sign challenge (missing/expired/replayed/re-rendered)."""


class SignatureVerificationFailed(Exception):
    """The E-IMZO signature is invalid/revoked."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AlreadySigned(Exception):
    """This company already signed the contract."""


class CannotCancel(Exception):
    """The contract can no longer be cancelled (a signature exists / terminal)."""


# ── Validation + requisites ───────────────────────────────────────────────────


def _validate_variables(schema: dict[str, object], variables: dict[str, object]) -> None:
    props_obj = schema.get("properties", {})
    props = props_obj if isinstance(props_obj, dict) else {}
    required_obj = schema.get("required", [])
    required = required_obj if isinstance(required_obj, list) else []
    errors: set[str] = set()
    for key in required:
        value = variables.get(str(key))
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.add(str(key))
    for key, value in variables.items():
        spec = props.get(key)
        if isinstance(spec, dict) and "enum" in spec:
            allowed = spec["enum"]
            if isinstance(allowed, list) and value not in allowed:
                errors.add(key)
    if errors:
        raise VariablesInvalid(sorted(errors))


def _requisites(db: Session, company: Company) -> dict[str, object]:
    """Full requisites for rendering (bank account decrypted — render path only)."""
    bank = (
        db.query(CompanyBankAccount)
        .filter(
            CompanyBankAccount.company_id == company.id,
            CompanyBankAccount.status != BankAccountStatus.archived,
        )
        .order_by(CompanyBankAccount.id)
        .first()
    )
    account_number = ""
    bank_mfo = ""
    if bank is not None:
        bank_mfo = bank.bank_mfo
        try:
            account_number = decrypt_pii(bank.account_number_enc)
        except Exception:  # noqa: BLE001 — undecryptable → leave blank in the document
            account_number = ""
    return {
        "legal_name": company.legal_name or company.tax_id,
        "inn": company.tax_id,
        "address": company.legal_address or "",
        "director": company.director_name or "",
        "bank_account": account_number,
        "bank_mfo": bank_mfo,
    }


# ── Create / render ───────────────────────────────────────────────────────────


def _assert_verified(company: Company) -> None:
    if company.status != CompanyStatus.verified:
        raise CompanyNotVerified(str(company.id))


def _render_and_store(db: Session, contract: Contract, template: ContractTemplate) -> None:
    """(Re)render the contract PDF from the template + current variables; store + hash."""
    template_html = storage_service.get_object_text(template.body_storage_path)
    initiator = _requisites(db, db.get(Company, contract.initiator_company_id))  # type: ignore[arg-type]
    counterparty = _requisites(db, db.get(Company, contract.counterparty_company_id))  # type: ignore[arg-type]
    generated_at = company_service.now_utc().strftime("%Y-%m-%d %H:%M UTC")
    variables = {**contract.variables, "title": contract.title}
    pdf = contract_render.render_contract_pdf(
        template_html, variables, initiator, counterparty,
        contract_public_id=str(contract.public_id), generated_at=generated_at,
    )
    # version_n = number of renders so far (bump each regenerate)
    version_n = (contract.variables.get("_render_n") if isinstance(contract.variables, dict) else 0) or 0
    path, sha = storage_service.store_contract_pdf(str(contract.public_id), int(version_n) + 1, pdf)
    contract.generated_document_path = path
    contract.document_sha256 = sha
    db.flush()


def create_contract(
    db: Session,
    initiator_company: Company,
    account: UserAccount,
    template: ContractTemplate,
    variables: dict[str, object],
    counterparty_company: Company,
    offer_id: int | None = None,
    title: str | None = None,
) -> Contract:
    """Create a draft contract between two verified companies; render the document."""
    if initiator_company.id == counterparty_company.id:
        raise NotAParty("initiator == counterparty")
    _assert_verified(initiator_company)
    _assert_verified(counterparty_company)
    _validate_variables(template.variables_schema, variables)

    contract = Contract(
        template_id=template.id,
        template_version=template.version,
        initiator_company_id=initiator_company.id,
        counterparty_company_id=counterparty_company.id,
        offer_id=offer_id,
        title=title or template.name_ru,
        variables=variables,
        status=ContractStatus.draft,
        created_by_user_account_id=account.id,
    )
    db.add(contract)
    db.flush()

    _render_and_store(db, contract, template)

    event_service.emit(
        db, event_types.CONTRACT_CREATED, "contract", contract.id,
        {"initiator_company_id": initiator_company.id, "counterparty_company_id": counterparty_company.id},
    )
    audit_service.write_audit(
        db, None, "contract.create", "contracts", str(contract.id),
        {"account_id": account.id, "template": template.code},
    )
    return contract


def update_variables(
    db: Session,
    contract: Contract,
    account: UserAccount,
    variables: dict[str, object],
    template: ContractTemplate,
) -> Contract:
    """Edit terms (draft only); re-render the document + sha256."""
    if contract.status != ContractStatus.draft:
        raise ContractNotEditable(str(contract.status))
    _validate_variables(template.variables_schema, variables)
    contract.variables = variables
    db.flush()
    _render_and_store(db, contract, template)
    audit_service.write_audit(
        db, None, "contract.update_variables", "contracts", str(contract.id),
        {"account_id": account.id},
    )
    return contract


# ── Transitions ───────────────────────────────────────────────────────────────


def _transition(db: Session, contract: Contract, to: ContractStatus) -> None:
    if to not in _TRANSITIONS.get(contract.status, set()):
        raise InvalidContractTransition(f"{contract.status} → {to}")
    contract.status = to
    db.flush()


def _assert_party(contract: Contract, company: Company) -> None:
    if company.id not in {contract.initiator_company_id, contract.counterparty_company_id}:
        raise NotAParty(str(company.id))


def send(db: Session, contract: Contract, account: UserAccount) -> Contract:
    """Initiator sends the draft to the counterparty (→ pending_counterparty)."""
    _transition(db, contract, ContractStatus.pending_counterparty)
    contract.sent_at = company_service.now_utc()
    db.flush()
    event_service.emit(
        db, event_types.CONTRACT_SENT, "contract", contract.id,
        {"counterparty_company_id": contract.counterparty_company_id},
    )
    _notify_company(db, contract.counterparty_company_id, "contract_incoming", contract)
    audit_service.write_audit(
        db, None, "contract.send", "contracts", str(contract.id), {"account_id": account.id}
    )
    return contract


def accept_terms(db: Session, contract: Contract, account: UserAccount) -> Contract:
    """Counterparty accepts the terms (→ pending_signatures)."""
    _transition(db, contract, ContractStatus.pending_signatures)
    event_service.emit(db, event_types.CONTRACT_SENT, "contract", contract.id, {"accepted": True})
    _notify_company(db, contract.initiator_company_id, "contract_accepted", contract)
    audit_service.write_audit(
        db, None, "contract.accept", "contracts", str(contract.id), {"account_id": account.id}
    )
    return contract


def decline(db: Session, contract: Contract, account: UserAccount, reason: str) -> Contract:
    """Counterparty declines (→ declined) with a reason."""
    _transition(db, contract, ContractStatus.declined)
    contract.declined_reason = reason
    db.flush()
    event_service.emit(
        db, event_types.CONTRACT_DECLINED, "contract", contract.id, {"reason": reason}
    )
    _notify_company(db, contract.initiator_company_id, "contract_declined", contract)
    audit_service.write_audit(
        db, None, "contract.decline", "contracts", str(contract.id),
        {"account_id": account.id, "reason": reason},
    )
    return contract


def cancel(db: Session, contract: Contract, account: UserAccount) -> Contract:
    """Initiator cancels (→ cancelled) — only while no signature exists."""
    signed = (
        db.query(ContractSignature).filter(ContractSignature.contract_id == contract.id).count()
    )
    if signed > 0 or contract.status not in {
        ContractStatus.draft,
        ContractStatus.pending_counterparty,
        ContractStatus.pending_signatures,
    }:
        raise CannotCancel(str(contract.status))
    _transition(db, contract, ContractStatus.cancelled)
    event_service.emit(db, event_types.CONTRACT_CANCELLED, "contract", contract.id, {})
    audit_service.write_audit(
        db, None, "contract.cancel", "contracts", str(contract.id), {"account_id": account.id}
    )
    return contract


# ── Signing (E-IMZO) ──────────────────────────────────────────────────────────


def _sign_challenge_value(contract: Contract) -> str:
    return f"contract:{contract.public_id}:{contract.document_sha256}"


def _challenge_key(contract_id: int, company_id: int) -> str:
    return f"eimzo:contract_ch:{contract_id}:{company_id}"


def issue_sign_challenge(
    db: Session,
    redis_client: redis.Redis[str],
    contract: Contract,
    company: Company,
    account: UserAccount,
) -> str:
    """Issue a single-use, document-hash-bound sign challenge for a party."""
    _assert_party(contract, company)
    if contract.status != ContractStatus.pending_signatures:
        raise InvalidContractTransition(str(contract.status))
    challenge = _sign_challenge_value(contract)
    redis_client.setex(
        _challenge_key(contract.id, company.id),
        settings.EIMZO_CHALLENGE_TTL_SECONDS,
        challenge,
    )
    return challenge


def sign(
    db: Session,
    redis_client: redis.Redis[str],
    contract: Contract,
    company: Company,
    account: UserAccount,
    pkcs7_b64: str,
) -> Contract:
    """Verify a party's E-IMZO signature and, when both are present, activate."""
    _assert_party(contract, company)
    if contract.status != ContractStatus.pending_signatures:
        raise InvalidContractTransition(str(contract.status))

    key = _challenge_key(contract.id, company.id)
    challenge = redis_client.getdel(key)
    if not isinstance(challenge, str):
        raise ChallengeExpired(str(contract.id))
    if challenge != _sign_challenge_value(contract):
        # document re-rendered after the challenge was issued → invalidate
        raise ChallengeExpired(str(contract.id))

    result = verify_pkcs7(pkcs7_b64, challenge)  # ProviderUnavailable propagates
    if not result.ok:
        raise SignatureVerificationFailed(result.error or "signature_invalid")
    cert_inn = result.signer.org_inn if result.signer else None
    if cert_inn and company.tax_id and cert_inn != company.tax_id:
        from app.services.eimzo_service import _mask_inn  # noqa: PLC0415

        raise CertCompanyMismatch(_mask_inn(cert_inn), _mask_inn(company.tax_id))

    if (
        db.query(ContractSignature)
        .filter(
            ContractSignature.contract_id == contract.id,
            ContractSignature.company_id == company.id,
        )
        .first()
        is not None
    ):
        raise AlreadySigned(str(company.id))

    # Immutable evidence (PKCS#7 to S3) + person-agnostic cert subject.
    try:
        pkcs7_bytes = base64.b64decode(pkcs7_b64)
    except (ValueError, TypeError):
        pkcs7_bytes = pkcs7_b64.encode("utf-8")
    path, sha = storage_service.store_eimzo_pkcs7(company.id, pkcs7_bytes)
    signer = result.signer
    evidence = SignatureEvidence(
        company_id=company.id,
        user_account_id=account.id,
        purpose=_PURPOSE_CONTRACT,
        challenge=challenge,
        pkcs7_storage_path=path,
        pkcs7_sha256=sha,
        cert_subject={
            "org_name": signer.org_name if signer else None,
            "org_inn": signer.org_inn if signer else None,
            "position": signer.position if signer else None,
            "serial_number": signer.serial_number if signer else None,
        },
        signed_at=company_service.now_utc(),
    )
    db.add(evidence)
    db.flush()

    db.add(
        ContractSignature(
            contract_id=contract.id,
            company_id=company.id,
            signed_by_user_account_id=account.id,
            signature_evidence_id=evidence.id,
        )
    )
    db.flush()

    event_service.emit(
        db, event_types.CONTRACT_SIGNED, "contract", contract.id, {"company_id": company.id}
    )
    audit_service.write_audit(
        db, None, "contract.sign", "contracts", str(contract.id),
        {"account_id": account.id, "company_id": company.id},
    )

    _maybe_activate(db, contract)
    return contract


def _maybe_activate(db: Session, contract: Contract) -> None:
    """Under a row lock: if both parties have signed, transition to active exactly once."""
    locked = db.execute(
        select(Contract).where(Contract.id == contract.id).with_for_update()
    ).scalar_one()
    if locked.status != ContractStatus.pending_signatures:
        return
    signer_companies = {
        cid
        for (cid,) in db.query(ContractSignature.company_id)
        .filter(ContractSignature.contract_id == contract.id)
        .all()
    }
    if {locked.initiator_company_id, locked.counterparty_company_id}.issubset(signer_companies):
        locked.status = ContractStatus.active
        locked.activated_at = company_service.now_utc()
        db.flush()
        event_service.emit(db, event_types.CONTRACT_ACTIVATED, "contract", contract.id, {})
        db.refresh(contract)


# ── Notifications (R2 portal_notifications; best-effort, in-tx) ────────────────


def _notify_company(db: Session, company_id: int, kind: str, contract: Contract) -> None:
    """Notify a company's active owner/manager members (in-portal, i18n-keyed)."""
    from app.models.companies import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    members = (
        db.query(CompanyMember.user_account_id)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.status == CompanyMemberStatus.active,
            CompanyMember.member_role.in_([CompanyMemberRole.owner, CompanyMemberRole.manager]),
        )
        .all()
    )
    title_key, body_key = notification_service.keys_for(kind)
    for (account_id,) in members:
        notification_service.notify_account(
            db,
            account_id=account_id,
            kind=kind,
            title_key=title_key,
            body_key=body_key,
            params={"title": contract.title},
            entity="contract",
            entity_id=str(contract.id),
        )


def now_utc() -> datetime.datetime:
    return company_service.now_utc()
