"""Portal company/verification schemas (R1 W5 — T5.1/T5.2).

Client-facing views: bank numbers are masked (`****{last4}`), and case/check views
expose only user-safe fields (check_type, status, human requirement) — never a
reviewer identity, internal error, or waive metadata.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    OfferAvailability,
    OfferSaleMode,
    PriceBasis,
    RegulationLevel,
    SellerOfferStatus,
)
from app.schemas.compliance import MissingOut
from app.schemas.marketplace import OfferFileRef
from app.schemas.substance import SubstanceBrief

# ── Inputs ────────────────────────────────────────────────────────────────────


class CompanyCreateIn(BaseModel):
    jurisdiction: str = "UZ"
    tax_id: str


class CompanyProfileUpdateIn(BaseModel):
    legal_name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    legal_address: str | None = None
    director_name: str | None = None


class RolesUpdateIn(BaseModel):
    roles: list[str]


class BankAccountIn(BaseModel):
    bank_mfo: str
    account_number: str
    bank_name: str | None = None
    currency: str = "UZS"


# ── Company / verification views ──────────────────────────────────────────────


class CheckOut(BaseModel):
    check_type: str
    status: str
    detail: dict[str, object] | None = None  # user-safe subset (e.g. missing docs)


class CaseOut(BaseModel):
    id: int
    case_type: str
    status: str
    submitted_at: datetime.datetime | None = None
    checks: list[CheckOut] = Field(default_factory=list)


class BusinessRoleOut(BaseModel):
    role: str
    status: str


class BankAccountOut(BaseModel):
    id: int
    bank_mfo: str
    bank_name: str | None = None
    account_masked: str
    currency: str
    status: str


class DocumentOut(BaseModel):
    id: int
    kind: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: str
    created_at: datetime.datetime


class CompanySummaryOut(BaseModel):
    id: int
    public_id: uuid.UUID
    jurisdiction: str
    tax_id: str
    legal_name: str | None = None
    short_name: str | None = None
    status: str
    verified_at: datetime.datetime | None = None
    #: Short-lived presigned GET URL (TTL ≤ 600 s) — there is no permanent public
    #: URL for media (FR-M4), so this is minted per response and is None when the
    #: company has no logo.
    logo_url: str | None = None
    active_case: CaseOut | None = None


class CompanyDetailOut(BaseModel):
    id: int
    public_id: uuid.UUID
    jurisdiction: str
    tax_id: str
    legal_name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    legal_address: str | None = None
    director_name: str | None = None
    status: str
    identity_locked: bool = False
    verified_at: datetime.datetime | None = None
    reverification_due_at: datetime.datetime | None = None
    #: See CompanySummaryOut.logo_url — presigned per response, never stored.
    logo_url: str | None = None
    roles: list[BusinessRoleOut] = Field(default_factory=list)
    bank_accounts: list[BankAccountOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    case: CaseOut | None = None


# ── Company offers (T5.2) ─────────────────────────────────────────────────────


class CompanyOfferIn(BaseModel):
    product_id: int | None = None
    product_text: str | None = Field(default=None, max_length=200)
    grade_text: str | None = Field(default=None, max_length=500)
    polymer_type: str | None = Field(default=None, max_length=200)
    availability: OfferAvailability = OfferAvailability.in_stock
    qty_available: decimal.Decimal | None = None
    qty_unit: str = "MT"
    price: decimal.Decimal | None = None
    currency: str = "USD"
    incoterms: PriceBasis = PriceBasis.unknown
    warehouse_city: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=2)
    min_order_qty: decimal.Decimal | None = None
    description: str | None = Field(default=None, max_length=2000)
    # ── How this company trades the offer (P4 W1) ─────────────────────────────
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    sale_mode: OfferSaleMode | None = None
    #: Deal-readiness badges. RFQ is opt-out (answering costs nothing); a contract
    #: and escrow are commitments, so they are opt-in.
    accepts_rfq: bool = True
    accepts_contract: bool = False
    accepts_escrow: bool = False
    # ── Chemistry (P5) ────────────────────────────────────────────────────────
    #: Registry link. A seller may instead type an identifier for something they
    #: believe is not in the registry (FR-C2) — the gate resolves that too.
    substance_id: int | None = None
    cas_number: str | None = Field(default=None, max_length=20)
    hs_code: str | None = Field(default=None, max_length=20)
    #: Regulation is concentration-dependent; leaving this empty is treated as
    #: "regulated", never as an exemption.
    declared_concentration_pct: decimal.Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _made_to_order_states_a_lead_time(self) -> CompanyOfferIn:
        """«Под заказ» carries no price (it is "по запросу"), so without a lead
        time the card tells a buyer nothing they can plan around.

        Deliberately NOT added to the Mini App's `SellerOfferCreate`: `webapp/` is
        frozen and cannot send the field, so requiring it there would break offer
        creation from Telegram.
        """
        if self.availability == OfferAvailability.on_order and self.lead_time_days is None:
            raise ValueError("lead_time_days is required for made-to-order offers")
        return self


class CompanyOfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: SellerOfferStatus
    product_id: int | None = None
    product_text: str | None = None
    grade_text: str | None = None
    polymer_type: str | None = None
    availability: OfferAvailability
    qty_available: decimal.Decimal | None = None
    qty_unit: str
    price: decimal.Decimal | None = None
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None = None
    country: str | None = None
    min_order_qty: decimal.Decimal | None = None
    description: str | None = None
    lead_time_days: int | None = None
    sale_mode: OfferSaleMode | None = None
    accepts_rfq: bool = True
    accepts_contract: bool = False
    accepts_escrow: bool = False
    #: Chemistry + the cached verdict (P5). `compliance_ok=False` on a draft is
    #: why it is a draft — the seller's requirements panel reads it.
    substance_id: int | None = None
    #: The registry row itself, so an edit form can show what was picked rather
    #: than only echoing the CAS back at the seller.
    substance: SubstanceBrief | None = None
    cas_number: str | None = None
    hs_code: str | None = None
    declared_concentration_pct: decimal.Decimal | None = None
    compliance_level: RegulationLevel | None = None
    compliance_ok: bool | None = None
    compliance_missing: list[MissingOut] | None = None
    moderation_note: str | None = None
    created_at: datetime.datetime
    #: Attached files in upload order (photos + documents), so the seller's own
    #: screens can render previews on a draft too — not just the public catalog.
    files: list[OfferFileRef] = Field(default_factory=list)
    #: The first photo. None when the offer has no photos (renders a placeholder).
    cover_file_id: int | None = None
