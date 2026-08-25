"""Portal contract request/response schemas (R3 Stage B — TB2.1)."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

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
    #: The deal this contract is being drawn up for.
    #:
    #: Without it `deals.contract_id` stays NULL, and the whole chain downstream
    #: never fires: `CONTRACT_ACTIVATED` finds no deal, the deal never reaches
    #: `contract_signed`, and escrow is never opened. The link exists in the model
    #: and was reachable only from tests until now.
    deal_id: int | None = None
    #: Which rail carries the signatures, frozen here like `escrow_payments.mode`.
    #:
    #: `eimzo` is our own: both parties sign a PDF we hold and we verify the
    #: PKCS#7 ourselves. `didox` hands the document to the EDI operator, which is
    #: what puts it in front of the tax authority — and needs an operator account
    #: on BOTH sides, so it is opt-in and never the default.
    signing_provider: Literal["eimzo", "didox"] = "eimzo"


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
    #: Which rail carries the signatures — `eimzo` (our own) or `didox`.
    #:
    #: The portal cannot pick a signing UI without it: on the Didox rail the
    #: parties sign a document held by the EDI operator, so the challenge/verify
    #: pair is replaced by a two-round-trip exchange and `signatures` stays empty
    #: by design (we never see the counterparty's PKCS#7 — they may have signed at
    #: any of the 27 operators).
    signing_provider: str = "eimzo"
    #: The Didox document backing this contract, when it is on that rail.
    didox_document_id: int | None = None
    #: Didox's own status ladder, verbatim: 0 draft · 1 awaiting partner ·
    #: 2 awaiting us · 3 signed · 4 rejected · 50 annulled by the tax committee.
    didox_status: int | None = None

