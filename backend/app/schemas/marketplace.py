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

from app.models.enums import (
    OfferAvailability,
    OfferFileKind,
    OfferRequestStatus,
    PriceBasis,
    SellerOfferStatus,
)

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
    availability: OfferAvailability = OfferAvailability.in_stock
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

class OfferFileRef(BaseModel):
    """Reference to an offer file (image / TDS / certificate) for client-side URLs."""

    id: int
    kind: OfferFileKind
    file_name: str

    model_config = {"from_attributes": True}


class CatalogSeller(BaseModel):
    """Public seller block on a catalog offer — company name + trust badge only.

    Contact details (phone/telegram) are intentionally OMITTED: buyer→seller contact
    goes through the admin-gated "Request an offer" flow, never directly. Staff see the
    full contact via ModerationSeller in the review queues.
    """

    company_name: str | None
    is_verified: bool

    model_config = {"from_attributes": True}


class ModerationSeller(BaseModel):
    """Full seller contact block — staff-only (dashboard moderation queue)."""

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
    availability: OfferAvailability
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
    files: list[OfferFileRef] = []
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class _CatalogOfferFields(BaseModel):
    """Shared catalog-offer fields WITHOUT the seller block.

    The `seller` block differs by audience — public `CatalogSeller` vs staff
    `ModerationSeller` — so it is declared on each concrete subclass instead of
    here. Overriding an inherited field with a narrower type trips mypy's field
    invariance (Incompatible types in assignment); a shared base that omits the
    field keeps both audiences mypy-clean and explicit.
    """

    id: int
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    polymer_type: str | None
    availability: OfferAvailability
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
    files: list[OfferFileRef] = []

    model_config = {"from_attributes": True}


class CatalogOfferOut(_CatalogOfferFields):
    """A public (approved) catalog offer with the seller's contact block."""

    seller: CatalogSeller


class PublicFeaturedOffer(BaseModel):
    """A public (approved) catalog offer for the ANONYMOUS marketing landing.

    Deliberately OMITS the seller contact block (company/contact/phone/telegram):
    the landing is served to unauthenticated browser visitors, and supplier contact
    details must stay behind Telegram auth (contact reveal happens in the
    authenticated /market screen). Only product/commercial fields + image refs are
    exposed here.
    """

    id: int
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    polymer_type: str | None
    availability: OfferAvailability
    qty_available: decimal.Decimal
    qty_unit: str
    price: decimal.Decimal
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None
    country: str | None
    published_at: datetime.datetime | None
    files: list[OfferFileRef] = []

    model_config = {"from_attributes": True}


class ModerationOfferOut(_CatalogOfferFields):
    """A pending offer for the dashboard moderation queue (adds status + full seller contact)."""

    status: SellerOfferStatus
    created_at: datetime.datetime
    seller: ModerationSeller


class CategoryCount(BaseModel):
    """Catalog category chip + count of approved offers."""

    code: str
    count: int


class ModerationDecision(BaseModel):
    """Approve/reject body (an optional note for the seller)."""

    note: str | None = Field(default=None, max_length=1000)


# ── Offer requests ("Request an offer" — admin-gated buyer→seller inquiry) ─────


class OfferRequestCreate(BaseModel):
    """Buyer inquiry against a specific offer. Identity comes from the verified dep."""

    quantity: decimal.Decimal | None = Field(default=None, gt=0)
    qty_unit: str = Field(default="MT", max_length=8)
    target_price: decimal.Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, max_length=3)
    message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _not_empty(self) -> OfferRequestCreate:
        """Require at least a quantity or a message so an inquiry carries some intent."""
        if self.quantity is None and not (self.message and self.message.strip()):
            raise ValueError("Provide a quantity or a message")
        return self


class OfferBrief(BaseModel):
    """A minimal offer summary embedded in an inquiry (buyer + admin views)."""

    id: int
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    price: decimal.Decimal
    currency: str
    qty_unit: str

    model_config = {"from_attributes": True}


class OfferRequestOut(BaseModel):
    """A buyer's own inquiry with its moderation status (buyer-facing)."""

    id: int
    offer_id: int
    status: OfferRequestStatus
    quantity: decimal.Decimal | None
    qty_unit: str
    target_price: decimal.Decimal | None
    currency: str | None
    message: str | None
    created_at: datetime.datetime
    offer: OfferBrief

    model_config = {"from_attributes": True}


class AdminOfferRequestBuyer(BaseModel):
    """Buyer contact block — shown ONLY to staff in the review queue (never to sellers)."""

    contact_name: str | None
    company_name: str | None
    phone: str | None
    telegram_user_id: int | None

    model_config = {"from_attributes": True}


class AdminOfferRequestSeller(BaseModel):
    """Seller contact block for the review queue (so staff can coordinate the deal)."""

    company_name: str | None
    phone: str | None
    telegram_username: str | None

    model_config = {"from_attributes": True}


class AdminOfferRequestOut(BaseModel):
    """A pending inquiry for the dashboard review queue (both parties' contacts)."""

    id: int
    status: OfferRequestStatus
    quantity: decimal.Decimal | None
    qty_unit: str
    target_price: decimal.Decimal | None
    currency: str | None
    message: str | None
    created_at: datetime.datetime
    offer: OfferBrief
    buyer: AdminOfferRequestBuyer
    seller: AdminOfferRequestSeller
