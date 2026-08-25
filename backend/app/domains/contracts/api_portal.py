"""Portal contract endpoints (R3 Stage B — TB2.1). Under /api/v1.

All routes require a portal account. Contract access is party-scoped: the account
must be an active member of the initiator OR counterparty company (else 404 — never
reveal existence).

This router used to also serve the counterparty picker at
`/portal/companies/directory`, which forced it to be included before the companies
router so that literal path could beat `/portal/companies/{company_id}`. P4 moved
that route to the companies router — a pure companies query belongs there — where
being declared above `/{company_id}` in the same file settles the match with no
cross-router include-order dependency at all. Nothing here depends on registration
order any more.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.domains.edi.models import DidoxDocument

import io
import json
import zipfile

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.domains.contracts import service as contract_service
from app.domains.contracts.eimzo import CertCompanyMismatch
from app.domains.contracts.eimzo_models import SignatureEvidence
from app.domains.contracts.models import Contract, ContractSignature, ContractTemplate
from app.domains.contracts.schemas import (
    ContractCreateIn,
    ContractDetailOut,
    ContractSummaryOut,
    DeclineIn,
    SignatureOut,
    SignChallengeOut,
    SignIn,
    TemplateOut,
    VariablesUpdateIn,
)
from app.integrations.eimzo import ProviderUnavailable
from app.models.enums import CompanyStatus, ContractStatus
from app.services import storage_service

router = APIRouter(prefix="/portal", tags=["portal-contracts"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _company_name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:
        return None
    return company.legal_name or company.short_name or company.tax_id


def _my_company_ids(db: Session, account: UserAccount) -> set[int]:
    return {c.id for c in company_service.list_my_companies(db, account)}


def _contract_and_role(
    db: Session, account: UserAccount, contract_id: int
) -> tuple[Contract, Company, str]:
    """Load a contract IFF the account is a member of a party; return (contract, party, role)."""
    contract = db.get(Contract, contract_id)
    my_ids = _my_company_ids(db, account)
    if contract is None or (
        contract.initiator_company_id not in my_ids
        and contract.counterparty_company_id not in my_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.initiator_company_id in my_ids:
        acting = db.get(Company, contract.initiator_company_id)
        role = "initiator"
    else:
        acting = db.get(Company, contract.counterparty_company_id)
        role = "counterparty"
    if acting is None:  # pragma: no cover — the FK guarantees the row exists
        raise RuntimeError(f"contract {contract.id} references a missing company")
    return contract, acting, role


def _summary_out(db: Session, contract: Contract, my_ids: set[int]) -> ContractSummaryOut:
    role = "initiator" if contract.initiator_company_id in my_ids else "counterparty"
    template = db.get(ContractTemplate, contract.template_id)
    return ContractSummaryOut(
        id=contract.id,
        public_id=contract.public_id,
        title=contract.title,
        status=str(contract.status),
        template_code=template.code if template else None,
        initiator_company_id=contract.initiator_company_id,
        initiator_name=_company_name(db, contract.initiator_company_id),
        counterparty_company_id=contract.counterparty_company_id,
        counterparty_name=_company_name(db, contract.counterparty_company_id),
        role=role,
        offer_id=contract.offer_id,
        created_at=contract.created_at,
        sent_at=contract.sent_at,
        activated_at=contract.activated_at,
    )


def _didox_document(db: Session, contract: Contract) -> DidoxDocument | None:
    """The live Didox document for this contract, if it is on that rail.

    Cheap and rail-gated: on the `eimzo` rail there is nothing to look up, and
    the overwhelming majority of contracts are on it.
    """
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    if contract.signing_provider != "didox":
        return None
    return (
        db.query(DidoxDocument)
        .filter(
            DidoxDocument.subject_kind == "contract",
            DidoxDocument.subject_id == contract.id,
            DidoxDocument.status.notin_([5, 55]),
        )
        .order_by(DidoxDocument.id.desc())
        .first()
    )


def _detail_out(db: Session, contract: Contract, my_ids: set[int]) -> ContractDetailOut:
    base = _summary_out(db, contract, my_ids)
    sigs = (
        db.query(ContractSignature)
        .filter(ContractSignature.contract_id == contract.id)
        .order_by(ContractSignature.id)
        .all()
    )
    didox_doc = _didox_document(db, contract)
    return ContractDetailOut(
        **base.model_dump(),
        signing_provider=contract.signing_provider,
        didox_document_id=didox_doc.id if didox_doc else None,
        didox_status=didox_doc.status if didox_doc else None,
        variables=contract.variables or {},
        declined_reason=contract.declined_reason,
        document_available=bool(contract.generated_document_path),
        document_sha256=contract.document_sha256,
        signatures=[
            SignatureOut(
                company_id=s.company_id,
                company_name=_company_name(db, s.company_id),
                signed_at=s.signed_at,
            )
            for s in sigs
        ],
    )


# ── templates ─────────────────────────────────────────────────────────────────


@router.get("/contract-templates", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> list[TemplateOut]:
    rows = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.is_active.is_(True))
        .order_by(ContractTemplate.code)
        .all()
    )
    return [
        TemplateOut(
            id=t.id, code=t.code, name_ru=t.name_ru, name_uz=t.name_uz, name_en=t.name_en,
            version=t.version, variables_schema=t.variables_schema,
        )
        for t in rows
    ]


# ── contract CRUD ─────────────────────────────────────────────────────────────


@router.post("/contracts", response_model=ContractDetailOut, status_code=status.HTTP_201_CREATED)
def create_contract(
    body: ContractCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    try:
        initiator = company_service.get_company_for(db, account, body.initiator_company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found") from exc

    counterparty = db.get(Company, body.counterparty_company_id)
    if counterparty is None or counterparty.status != CompanyStatus.verified:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="counterparty_not_verified"
        )
    template = db.get(ContractTemplate, body.template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    try:
        contract = contract_service.create_contract(
            db, initiator, account, template, body.variables, counterparty,
            offer_id=body.offer_id, title=body.title,
            signing_provider=body.signing_provider,
        )
    except contract_service.CompanyNotVerified as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_not_verified") from exc
    except contract_service.VariablesInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_variables", "fields": exc.fields},
        ) from exc
    except contract_service.NotAParty as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_parties") from exc

    if body.deal_id is not None:
        _link_to_deal(db, account, contract, body.deal_id)

    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


def _link_to_deal(
    db: Session, account: UserAccount, contract: Contract, deal_id: int
) -> None:
    """Point the deal at this contract, in the SAME transaction as the create.

    A router composing two services, which is allowed — `deals` still owns the
    link and `contracts` still never writes to a deals table. Doing it here rather
    than inside `contract_service` keeps that boundary intact while closing the
    gap that left every portal-created contract orphaned from its deal.
    """
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415

    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    # A member of EITHER party may draw up the contract.
    my_companies = _my_company_ids(db, account)
    if not {deal.buyer_company_id, deal.seller_company_id} & my_companies:
        # Same rule as everywhere else in the portal: a stranger learns nothing.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    try:
        deal_service.attach_contract(db, deal, contract, account)
    except deal_service.NotDealParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="not_deal_participant"
        ) from exc
    except deal_service.DealAlreadyOpen as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="deal_has_contract"
        ) from exc


@router.get("/contracts", response_model=list[ContractSummaryOut])
def list_contracts(
    company_id: int | None = Query(default=None),
    role: str | None = Query(default=None),
    contract_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[ContractSummaryOut]:
    my_ids = _my_company_ids(db, account)
    if not my_ids:
        return []
    stmt = select(Contract).where(
        or_(
            Contract.initiator_company_id.in_(my_ids),
            Contract.counterparty_company_id.in_(my_ids),
        )
    )
    if company_id is not None:
        if role == "initiator":
            stmt = stmt.where(Contract.initiator_company_id == company_id)
        elif role == "counterparty":
            stmt = stmt.where(Contract.counterparty_company_id == company_id)
        else:
            stmt = stmt.where(
                or_(
                    Contract.initiator_company_id == company_id,
                    Contract.counterparty_company_id == company_id,
                )
            )
    if contract_status:
        stmt = stmt.where(Contract.status == contract_status)
    stmt = stmt.order_by(Contract.id.desc())
    return [_summary_out(db, c, my_ids) for c in db.execute(stmt).scalars().all()]


@router.get("/contracts/{contract_id}", response_model=ContractDetailOut)
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, _acting, _role = _contract_and_role(db, account, contract_id)
    return _detail_out(db, contract, _my_company_ids(db, account))


@router.patch("/contracts/{contract_id}", response_model=ContractDetailOut)
def update_contract(
    contract_id: int,
    body: VariablesUpdateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, acting, role = _contract_and_role(db, account, contract_id)
    if role != "initiator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only_initiator")
    template = db.get(ContractTemplate, contract.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        contract_service.update_variables(db, contract, account, body.variables, template)
    except contract_service.ContractNotEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_editable") from exc
    except contract_service.VariablesInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_variables", "fields": exc.fields},
        ) from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


# ── lifecycle actions ─────────────────────────────────────────────────────────


def _transition_error(exc: contract_service.InvalidContractTransition) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invalid_transition")


@router.post("/contracts/{contract_id}/send", response_model=ContractDetailOut)
def send_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, _acting, role = _contract_and_role(db, account, contract_id)
    if role != "initiator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only_initiator")
    try:
        contract_service.send(db, contract, account)
    except contract_service.InvalidContractTransition as exc:
        raise _transition_error(exc) from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


@router.post("/contracts/{contract_id}/accept", response_model=ContractDetailOut)
def accept_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, _acting, role = _contract_and_role(db, account, contract_id)
    if role != "counterparty":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only_counterparty")
    try:
        contract_service.accept_terms(db, contract, account)
    except contract_service.InvalidContractTransition as exc:
        raise _transition_error(exc) from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


@router.post("/contracts/{contract_id}/decline", response_model=ContractDetailOut)
def decline_contract(
    contract_id: int,
    body: DeclineIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, _acting, role = _contract_and_role(db, account, contract_id)
    if role != "counterparty":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only_counterparty")
    try:
        contract_service.decline(db, contract, account, body.reason)
    except contract_service.InvalidContractTransition as exc:
        raise _transition_error(exc) from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


@router.post("/contracts/{contract_id}/cancel", response_model=ContractDetailOut)
def cancel_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ContractDetailOut:
    contract, _acting, role = _contract_and_role(db, account, contract_id)
    if role != "initiator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only_initiator")
    try:
        contract_service.cancel(db, contract, account)
    except contract_service.CannotCancel as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot_cancel") from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


# ── signing ───────────────────────────────────────────────────────────────────


@router.post("/contracts/{contract_id}/sign/challenge", response_model=SignChallengeOut)
def sign_challenge(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> SignChallengeOut:
    contract, acting, _role = _contract_and_role(db, account, contract_id)
    try:
        challenge = contract_service.issue_sign_challenge(db, redis_client, contract, acting, account)
    except contract_service.InvalidContractTransition as exc:
        raise _transition_error(exc) from exc
    return SignChallengeOut(challenge=challenge)


@router.post("/contracts/{contract_id}/sign", response_model=ContractDetailOut)
def sign_contract(
    contract_id: int,
    body: SignIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> ContractDetailOut:
    contract, acting, _role = _contract_and_role(db, account, contract_id)
    try:
        contract_service.sign(db, redis_client, contract, acting, account, body.pkcs7)
    except contract_service.ChallengeExpired as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="challenge_expired") from exc
    except CertCompanyMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "cert_company_mismatch", "cert_inn": exc.cert_inn_masked},
        ) from exc
    except contract_service.SignatureVerificationFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "signature_failed", "reason": exc.reason},
        ) from exc
    except contract_service.AlreadySigned as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_signed") from exc
    except contract_service.InvalidContractTransition as exc:
        raise _transition_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="eimzo_unavailable"
        ) from exc
    db.commit()
    return _detail_out(db, contract, _my_company_ids(db, account))


# ── document + bundle ─────────────────────────────────────────────────────────


@router.get("/contracts/{contract_id}/document")
def contract_document(
    contract_id: int,
    as_: str = Query(default="redirect", alias="as"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Presigned PDF. `?as=url` returns {url} (for inline preview — an iframe can't
    carry the Bearer token); default 307-redirects to the presigned S3 object."""
    contract, _acting, _role = _contract_and_role(db, account, contract_id)
    if not contract.generated_document_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No document")
    url = storage_service.presign_object(contract.generated_document_path, ttl=600)
    if as_ == "url":
        return JSONResponse({"url": url})
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/contracts/{contract_id}/bundle")
def contract_bundle(
    contract_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    contract, _acting, _role = _contract_and_role(db, account, contract_id)
    if contract.status != ContractStatus.active or not contract.generated_document_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_active")

    sigs = (
        db.query(ContractSignature)
        .filter(ContractSignature.contract_id == contract.id)
        .order_by(ContractSignature.id)
        .all()
    )
    info: dict[str, object] = {
        "contract_public_id": str(contract.public_id),
        "title": contract.title,
        "document_sha256": contract.document_sha256,
        "signers": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("contract.pdf", storage_service.get_object_bytes(contract.generated_document_path))
        for idx, sig in enumerate(sigs, start=1):
            evidence = db.get(SignatureEvidence, sig.signature_evidence_id)
            if evidence is not None:
                zf.writestr(
                    f"signature_{idx}.p7s",
                    storage_service.get_object_bytes(evidence.pkcs7_storage_path),
                )
                signers = info["signers"]
                if not isinstance(signers, list):  # pragma: no cover — set as a list above
                    raise RuntimeError("signature info 'signers' is not a list")
                signers.append(
                    {
                        "company_id": sig.company_id,
                        "company_name": _company_name(db, sig.company_id),
                        "signed_at": sig.signed_at.isoformat(),
                        "pkcs7_sha256": evidence.pkcs7_sha256,
                    }
                )
        zf.writestr("verification.json", json.dumps(info, ensure_ascii=False, indent=2))

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="contract_{contract.public_id}.zip"'},
    )
