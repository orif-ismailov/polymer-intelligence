"""
Pydantic schemas for the seller marketplace (Phase 2).

Covers seller-offer creation (open self-serve: the seller is upserted from the
verified initData identity), the seller's own-offers view, the public catalog
representation (approved offers + seller contact), category counts, and the
dashboard moderation decision.

No identity fields on create — the seller is resolved from the verified
X-Telegram-Init-Data header (get_current_client), never the body.
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import PriceBasis, SellerOfferStatus

# ── Create ──────────────────────────────────────────────────────────────────────

class SellerOfferCreate(BaseModel):
    """Body for POST /webapp/seller/offers (submitted straight to moderation).

    product_id OR product_text is required; qty_available and price must be > 0.
    The seller contact fields upsert the caller's Seller record.
    """

    product_id: int | None = None
    product_text: str | None = Field(default=None, max_length=200)
    grade_text: str | None = Field(default=None, max_length=500)
    polymer_type: str | None = Field(default=None, max_length=200)
    qty_available: decimal.Decimal
    qty_unit: str = "MT"
    price: decimal.Decimal
    currency: str = "USD"
    incoterms: PriceBasis = PriceBasis.unknown
    warehouse_city: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=2)
    min_order_qty: decimal.Decimal | None = None
    description: str | None = Field(default=None, max_length=2000)
    # Seller contact — upserts the Seller for this Telegram identity.
    company_name: str | None = Field(default=None, max_length=300)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    telegram_username: str | None = Field(default=None, max_length=100)

    @field_validator("qty_available")
    @classmethod
    def _qty_positive(cls, v: decimal.Decimal) -> decimal.Decimal:
        if v <= 0:
            raise ValueError("qty_available must be greater than 0")
        return v

    @field_validator("price")
    @classmethod
    def _price_positive(cls, v: decimal.Decimal) -> decimal.Decimal:
        if v <= 0:
            raise ValueError("price must be greater than 0")
        return v

    @model_validator(mode="after")
    def _product_present(self) -> SellerOfferCreate:
        if self.product_id is None and not (
            self.product_text is not None and self.product_text.strip() != ""
        ):
            raise ValueError("Either 'product_id' or 'product_text' must be provided")
        return self


# ── Read-side ───────────────────────────────────────────────────────────────────

class CatalogSeller(BaseModel):
    """Seller contact block shown on a public catalog offer."""

    company_name: str | None
    contact_name: str | None
    phone: str | None
    telegram_username: str | None
    is_verified: bool

    model_config = {"from_attributes": True}


class SellerOfferOut(BaseModel):
    """A seller's own offer (includes moderation status)."""

    id: int
    status: SellerOfferStatus
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    polymer_type: str | None
    qty_available: decimal.Decimal
    qty_unit: str
    price: decimal.Decimal
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None
    country: str | None
    min_order_qty: decimal.Decimal | None
    description: str | None
    moderation_note: str | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CatalogOfferOut(BaseModel):
    """A public (approved) catalog offer with the seller's contact block."""

    id: int
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    polymer_type: str | None
    qty_available: decimal.Decimal
    qty_unit: str
    price: decimal.Decimal
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None
    country: str | None
    min_order_qty: decimal.Decimal | None
    description: str | None
    published_at: datetime.datetime | None
    seller: CatalogSeller

    model_config = {"from_attributes": True}


class ModerationOfferOut(CatalogOfferOut):
    """A pending offer for the dashboard moderation queue (adds status/created_at)."""

    status: SellerOfferStatus
    created_at: datetime.datetime


class CategoryCount(BaseModel):
    """Catalog category chip + count of approved offers."""

    code: str
    count: int


class ModerationDecision(BaseModel):
    """Approve/reject body (an optional note for the seller)."""

    note: str | None = Field(default=None, max_length=1000)
