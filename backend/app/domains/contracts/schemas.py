"""Portal contract request/response schemas (R3 Stage B — TB2.1)."""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domains.contracts.templates import KINDS


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
    #: The company's saved terms the form was filled from, if any. The values
    #: themselves arrive in `variables` — the user may have changed them since.
    term_preset_id: int | None = None


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


# ── Contract-template AUTHORING (staff) ───────────────────────────────────────
#
# Read and write shapes are kept deliberately symmetric. The bug this repo has paid
# for before is a read schema returning FEWER fields than the write schema accepts:
# the screen loads a row, the omitted field comes back absent, the next save writes
# the absence, and the value is gone with nobody having touched it. Here that would
# erase `variables_schema` — the declaration of what a template's form asks for.

#: Stable identifier, e.g. SUPPLY_V3. Upper snake so it reads the same in an audit
#: row, an S3 key and a runbook.
_TEMPLATE_CODE = r"^[A-Z][A-Z0-9_]{2,63}$"



class TemplateSummaryOut(BaseModel):
    """One row of the list screen. No body — see `TemplateDetailOut`."""

    id: int
    code: str
    kind: str
    name_ru: str
    name_uz: str | None = None
    name_en: str | None = None
    version: int
    is_active: bool
    created_at: datetime.datetime
    #: Contracts referencing this template. Signed ones cannot change (their PDF is
    #: frozen); drafts re-render, so this is what an editor needs to see.
    usage_count: int = 0


class TemplateDetailOut(TemplateSummaryOut):
    body: str
    variables_schema: dict[str, object] = Field(default_factory=dict)
    body_storage_path: str
    #: Advisory only — a saved template always has an empty `unknown`.
    warnings: list[str] = Field(default_factory=list)


class TemplateCreateIn(BaseModel):
    code: str = Field(pattern=_TEMPLATE_CODE, description="Stable identifier, e.g. SUPPLY_V3")
    kind: Literal["contract", "sample_letter"] = "contract"
    name_ru: str = Field(min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    variables_schema: dict[str, object] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        # Belt and braces with the Literal: KINDS mirrors the DB CHECK constraint,
        # and the two must not be able to drift apart silently.
        if v not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        return v


class TemplateUpdateIn(BaseModel):
    """`code` and `kind` are absent on purpose — see `templates.update_template`."""

    name_ru: str = Field(min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    #: Omit to leave the stored body untouched; an unchanged body does not bump the
    #: version, so re-saving the metadata does not create a phantom revision.
    body: str | None = Field(default=None, min_length=1)
    variables_schema: dict[str, object] | None = None
    is_active: bool = True


class TemplateActiveIn(BaseModel):
    is_active: bool


class TemplateCheckIn(BaseModel):
    """A body to validate or preview without saving anything."""

    body: str = Field(min_length=1)
    kind: Literal["contract", "sample_letter"] = "contract"
    variables_schema: dict[str, object] = Field(default_factory=dict)


class TemplateCheckOut(BaseModel):
    ok: bool
    #: `{{ names }}` the renderer cannot fill. These BLOCK a save, because
    #: `render._fill` turns each one into an empty string with no error anywhere —
    #: a legal document with a hole and nothing to notice it by.
    unknown: list[str] = Field(default_factory=list)
    used: list[str] = Field(default_factory=list)
    renderable: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TemplatePreviewOut(BaseModel):
    """Rendered HTML with visible `[stand_in]` tokens in place of real values."""

    html: str
    warnings: list[str] = Field(default_factory=list)


class TermPresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    terms: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class TermPresetOut(BaseModel):
    id: int
    name: str
    terms: dict[str, str]
    updated_at: datetime.datetime


class TermPresetListOut(BaseModel):
    items: list[TermPresetOut]
    #: Owners and managers edit; every member reads.
    can_edit: bool


class SpecificationIn(BaseModel):
    """A framework contract's next specification: its lines and terms."""

    variables: dict[str, object] = Field(default_factory=dict)


class SpecificationLineOut(BaseModel):
    ord_no: int
    product: str
    qty: decimal.Decimal | None
    unit: str | None
    price_without_vat: decimal.Decimal | None
    vat_rate: int | None
    amount_without_vat: decimal.Decimal | None


class SpecificationOut(BaseModel):
    id: int
    number: int
    spec_date: datetime.date
    status: str
    amount_without_vat: decimal.Decimal | None
    vat_sum: decimal.Decimal | None
    amount_with_vat: decimal.Decimal | None
    document_available: bool
    #: The «Произвольный документ» at Didox, once the seller has sent it.
    didox_document_id: int | None = None
    #: Didox's status as THIS reader sees it (1/2 mirrored), like the contract's.
    didox_status: int | None = None
    lines: list[SpecificationLineOut] = Field(default_factory=list)


class SpecificationListOut(BaseModel):
    items: list[SpecificationOut]
    #: A signed framework contract takes specifications; nothing else does.
    can_create: bool
    #: The reader's company sells under this contract — it sends specifications to Didox.
    is_seller: bool = False
