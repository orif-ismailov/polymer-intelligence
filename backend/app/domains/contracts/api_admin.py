"""Staff contract oversight API (R3 Stage B — TB2.2). Under /api/v1/admin.

Read-only: analysts/admins list + inspect contracts (parties, status, signatures,
audit timeline, document access). No staff mutation of contracts in R3 — dispute
tooling is future Deal Lifecycle work.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import Text, cast, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.contracts.models import Contract, ContractSignature, ContractTemplate
from app.models.staff import AuditLog
from app.services import storage_service

router = APIRouter(prefix="/admin", tags=["admin-contracts"], dependencies=[Depends(require_analyst_or_admin)])


class AdminSignatureOut(BaseModel):
    company_id: int
    company_name: str | None = None
    signed_at: datetime.datetime


class AdminTimelineOut(BaseModel):
    action: str
    at: datetime.datetime
    details: dict[str, object] = Field(default_factory=dict)


class AdminContractOut(BaseModel):
    id: int
    public_id: uuid.UUID
    title: str
    status: str
    template_code: str | None = None
    initiator_company_id: int
    initiator_name: str | None = None
    counterparty_company_id: int
    counterparty_name: str | None = None
    created_at: datetime.datetime
    sent_at: datetime.datetime | None = None
    activated_at: datetime.datetime | None = None
    declined_reason: str | None = None
    document_available: bool = False
    document_sha256: str | None = None


class AdminContractDetailOut(AdminContractOut):
    variables: dict[str, object] = Field(default_factory=dict)
    signatures: list[AdminSignatureOut] = Field(default_factory=list)
    timeline: list[AdminTimelineOut] = Field(default_factory=list)


def _name(db: Session, company_id: int) -> str | None:
    company = db.get(Company, company_id)
    if company is None:
        return None
    return company.legal_name or company.short_name or company.tax_id


def _out(db: Session, contract: Contract) -> AdminContractOut:
    template = db.get(ContractTemplate, contract.template_id)
    return AdminContractOut(
        id=contract.id,
        public_id=contract.public_id,
        title=contract.title,
        status=str(contract.status),
        template_code=template.code if template else None,
        initiator_company_id=contract.initiator_company_id,
        initiator_name=_name(db, contract.initiator_company_id),
        counterparty_company_id=contract.counterparty_company_id,
        counterparty_name=_name(db, contract.counterparty_company_id),
        created_at=contract.created_at,
        sent_at=contract.sent_at,
        activated_at=contract.activated_at,
        declined_reason=contract.declined_reason,
        document_available=bool(contract.generated_document_path),
        document_sha256=contract.document_sha256,
    )


@router.get("/contracts", response_model=list[AdminContractOut])
def list_contracts(
    contract_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> list[AdminContractOut]:
    stmt = select(Contract)
    if contract_status:
        stmt = stmt.where(Contract.status == contract_status)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Contract.title.ilike(like), cast(Contract.public_id, Text).ilike(like))
        )
    stmt = stmt.order_by(Contract.id.desc()).limit(200)
    return [_out(db, c) for c in db.execute(stmt).scalars().all()]


@router.get("/contracts/{contract_id}", response_model=AdminContractDetailOut)
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
) -> AdminContractDetailOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    base = _out(db, contract)
    sigs = (
        db.query(ContractSignature)
        .filter(ContractSignature.contract_id == contract.id)
        .order_by(ContractSignature.id)
        .all()
    )
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity == "contracts", AuditLog.entity_id == str(contract.id))
        .order_by(AuditLog.id)
        .all()
    )
    return AdminContractDetailOut(
        **base.model_dump(),
        variables=contract.variables or {},
        signatures=[
            AdminSignatureOut(company_id=s.company_id, company_name=_name(db, s.company_id), signed_at=s.signed_at)
            for s in sigs
        ],
        timeline=[
            AdminTimelineOut(action=a.action, at=a.created_at, details=a.details or {}) for a in audit
        ],
    )


@router.get("/contracts/{contract_id}/document")
def contract_document(
    contract_id: int,
    as_: str = Query(default="redirect", alias="as"),
    db: Session = Depends(get_db),
) -> Response:
    contract = db.get(Contract, contract_id)
    if contract is None or not contract.generated_document_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No document")
    url = storage_service.presign_object(contract.generated_document_path, ttl=600)
    if as_ == "url":
        return JSONResponse({"url": url})
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
