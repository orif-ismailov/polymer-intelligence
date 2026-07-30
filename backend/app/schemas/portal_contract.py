"""Portal contract request/response schemas (R3 Stage B — TB2.1)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    id: int
    code: str
    name_ru: str
    name_uz: str | None = None
    name_en: str | None = None
    version: int
    variables_schema: dict[str, object]


class ContractCreateIn(BaseModel):
    initiator_company_id: int
    counterparty_company_id: int
    template_id: int
    variables: dict[str, object] = Field(default_factory=dict)
    offer_id: int | None = None
    title: str | None = Field(default=None, max_length=300)


class VariablesUpdateIn(BaseModel):
    variables: dict[str, object] = Field(default_factory=dict)


class DeclineIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class SignIn(BaseModel):
    pkcs7: str = Field(min_length=1)


class SignChallengeOut(BaseModel):
    challenge: str


class SignatureOut(BaseModel):
    company_id: int
    company_name: str | None = None
    signed_at: datetime.datetime


class ContractSummaryOut(BaseModel):
    id: int
    public_id: uuid.UUID
    title: str
    status: str
    template_code: str | None = None
    initiator_company_id: int
    initiator_name: str | None = None
    counterparty_company_id: int
    counterparty_name: str | None = None
    role: str                                                 # 'initiator' | 'counterparty'
    offer_id: int | None = None
    created_at: datetime.datetime
    sent_at: datetime.datetime | None = None
    activated_at: datetime.datetime | None = None


class ContractDetailOut(ContractSummaryOut):
    variables: dict[str, object] = Field(default_factory=dict)
    declined_reason: str | None = None
    document_available: bool = False
    document_sha256: str | None = None
    signatures: list[SignatureOut] = Field(default_factory=list)


class DirectoryCompanyOut(BaseModel):
    id: int
    public_id: uuid.UUID
    legal_name: str | None = None
    tax_id: str
    roles: list[str] = Field(default_factory=list)
    verified: bool = True
