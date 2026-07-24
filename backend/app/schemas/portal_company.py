"""Portal company/verification schemas (R1 W5 — T5.1/T5.2).

Client-facing views: bank numbers are masked (`****{last4}`), and case/check views
expose only user-safe fields (check_type, status, human requirement) — never a
reviewer identity, internal error, or waive metadata.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OfferAvailability, PriceBasis, SellerOfferStatus

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
    verified_at: datetime.datetime | None = None
    reverification_due_at: datetime.datetime | None = None
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
    moderation_note: str | None = None
    created_at: datetime.datetime
