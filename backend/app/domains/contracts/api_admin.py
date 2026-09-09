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

from app.api.deps import require_admin, require_page
from app.core.db import get_db
from app.domains.companies.models import Company
from app.domains.contracts import templates as template_service
from app.domains.contracts.models import Contract, ContractSignature, ContractTemplate
from app.domains.contracts.schemas import (
    TemplateActiveIn,
    TemplateCheckIn,
    TemplateCheckOut,
    TemplateCreateIn,
    TemplateDetailOut,
    TemplatePreviewOut,
    TemplateSummaryOut,
    TemplateUpdateIn,
)
from app.models.staff import AuditLog, StaffUser
from app.services import storage_service

router = APIRouter(prefix="/admin", tags=["admin-contracts"], dependencies=[Depends(require_page("contracts", "read"))])


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


# ── Contract templates (authoring) ────────────────────────────────────────────
#
# `contract_templates` had one writer (the seeder) and no admin route until this
# section existed, which made two things impossible: installing the real legal text
# over the shipped DEV PLACEHOLDER (a launch blocker recorded in deploy/CLAUDE.md),
# and recovering a database whose seeders had not run — with the table empty NO
# contract can be created and the whole signing chain is dead.
#
# Reads sit on the router's `contracts:read` grant. WRITES require an administrator
# regardless of that grant: these bodies are the legal text two companies e-sign,
# and handing someone the contracts page must not hand them the power to rewrite it.


def _summary(template: ContractTemplate, usage: int) -> TemplateSummaryOut:
    return TemplateSummaryOut(
        id=template.id,
        code=template.code,
        kind=template.kind,
        name_ru=template.name_ru,
        name_uz=template.name_uz,
        name_en=template.name_en,
        version=template.version,
        is_active=template.is_active,
        created_at=template.created_at,
        usage_count=usage,
    )


def _template_or_404(db: Session, template_id: int) -> ContractTemplate:
    template = template_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


def _invalid_body(exc: template_service.TemplateBodyInvalid) -> HTTPException:
    """422 naming every placeholder the renderer cannot fill.

    The names matter more than the status: `render._fill` substitutes an empty
    string for an unknown `{{ name }}`, so the alternative to this error is a signed
    document with a silent hole in it.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "template_body_invalid", "unknown": exc.unknown},
    )


@router.get("/contract-templates", response_model=list[TemplateSummaryOut])
def list_contract_templates(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> list[TemplateSummaryOut]:
    usage = template_service.usage_counts(db)
    return [
        _summary(t, usage.get(t.id, 0))
        for t in template_service.list_templates(db, include_inactive=include_inactive)
    ]


@router.get("/contract-templates/{template_id}", response_model=TemplateDetailOut)
def get_contract_template(
    template_id: int, db: Session = Depends(get_db)
) -> TemplateDetailOut:
    template = _template_or_404(db, template_id)
    body = template_service.load_body(template)
    report = template_service.validate_body(body, template.kind, template.variables_schema or {})
    usage = template_service.usage_counts(db).get(template.id, 0)
    return TemplateDetailOut(
        **_summary(template, usage).model_dump(),
        body=body,
        variables_schema=template.variables_schema or {},
        body_storage_path=template.body_storage_path,
        warnings=report.warnings,
    )


@router.post(
    "/contract-templates", response_model=TemplateDetailOut, status_code=status.HTTP_201_CREATED
)
def create_contract_template(
    body: TemplateCreateIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> TemplateDetailOut:
    try:
        template = template_service.create_template(
            db,
            code=body.code,
            kind=body.kind,
            name_ru=body.name_ru,
            name_uz=body.name_uz,
            name_en=body.name_en,
            body=body.body,
            variables_schema=body.variables_schema,
            is_active=body.is_active,
            staff_user_id=staff.id,
        )
    except template_service.DuplicateCode as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "duplicate_code", "code": exc.code},
        ) from exc
    except template_service.TemplateBodyInvalid as exc:
        raise _invalid_body(exc) from exc
    db.commit()
    return get_contract_template(template.id, db)


@router.put("/contract-templates/{template_id}", response_model=TemplateDetailOut)
def update_contract_template(
    template_id: int,
    body: TemplateUpdateIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> TemplateDetailOut:
    template = _template_or_404(db, template_id)
    try:
        template_service.update_template(
            db,
            template,
            name_ru=body.name_ru,
            name_uz=body.name_uz,
            name_en=body.name_en,
            body=body.body,
            variables_schema=body.variables_schema,
            is_active=body.is_active,
            staff_user_id=staff.id,
        )
    except template_service.TemplateBodyInvalid as exc:
        raise _invalid_body(exc) from exc
    db.commit()
    return get_contract_template(template_id, db)


@router.patch("/contract-templates/{template_id}/active", response_model=TemplateSummaryOut)
def set_contract_template_active(
    template_id: int,
    body: TemplateActiveIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_admin),
) -> TemplateSummaryOut:
    template = _template_or_404(db, template_id)
    template_service.set_active(db, template, is_active=body.is_active, staff_user_id=staff.id)
    db.commit()
    return _summary(template, template_service.usage_counts(db).get(template.id, 0))


@router.post("/contract-templates/check", response_model=TemplateCheckOut)
def check_contract_template(body: TemplateCheckIn) -> TemplateCheckOut:
    """Validate a draft body without saving. Backs the editor's inline errors."""
    report = template_service.validate_body(body.body, body.kind, body.variables_schema)
    return TemplateCheckOut(
        ok=report.ok,
        unknown=report.unknown,
        used=report.used,
        renderable=sorted(template_service.renderable_names(body.kind, body.variables_schema)),
        warnings=report.warnings,
    )


@router.post("/contract-templates/preview", response_model=TemplatePreviewOut)
def preview_contract_template(body: TemplateCheckIn) -> TemplatePreviewOut:
    """Render a draft with visible `[stand_in]` tokens.

    Stand-ins rather than blanks on purpose: filled with realistic-looking values a
    missing placeholder is invisible, which is the exact failure being guarded
    against. A hole in this output is a hole in the template.
    """
    report = template_service.validate_body(body.body, body.kind, body.variables_schema)
    return TemplatePreviewOut(
        html=template_service.preview(body.body, body.kind, body.variables_schema),
        warnings=report.warnings + ([f"not renderable: {n}" for n in report.unknown]),
    )
