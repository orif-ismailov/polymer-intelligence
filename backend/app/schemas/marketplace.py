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
    # Optional: «под заказ» (on_order) offers carry no qty/price (price is "по запросу").
    # The availability rule below forces them to null for on_order and requires them
    # (positive) for in_stock.
    qty_available: decimal.Decimal | None = None
    qty_unit: str = "MT"
    price: decimal.Decimal | None = None
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

    @field_validator("qty_available", "price")
    @classmethod
    def _positive_when_present(cls, v: decimal.Decimal | None) -> decimal.Decimal | None:
        # None is allowed here (made-to-order «под заказ»); _availability_pricing below
        # decides when a value is required. When one IS given, it must be positive.
        if v is not None and v <= 0:
            raise ValueError("must be greater than 0")
        return v

    @model_validator(mode="after")
    def _availability_pricing(self) -> SellerOfferCreate:
        """«Под заказ» → no qty/price (price is "по запросу"); «в наличии» → both required."""
        if self.availability == OfferAvailability.on_order:
            # Never store a qty/price for made-to-order offers, even if one was sent.
            self.qty_available = None
            self.price = None
        else:
            if self.qty_available is None:
                raise ValueError("qty_available is required for in-stock offers")
            if self.price is None:
                raise ValueError("price is required for in-stock offers")
        return self

    @model_validator(mode="after")
    def _product_present(self) -> SellerOfferCreate:
        if self.product_id is None and not (
            self.product_text is not None and self.product_text.strip() != ""
        ):
            raise ValueError("Either 'product_id' or 'product_text' must be provided")
        return self


class SellerOfferUpdate(SellerOfferCreate):
    """A seller's revision to their own offer — same shape + validation as create.

    Full-replacement of the offer's fields (the client resends the current values and
    changes what it wants). Editing an offer that is already public (approved) — or one
    that was rejected — re-enters moderation; the service owns that transition.
    """


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
    qty_available: decimal.Decimal | None  # null for «под заказ» (on_order)
    qty_unit: str
    price: decimal.Decimal | None  # null for «под заказ» — shown as "по запросу"
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
    qty_available: decimal.Decimal | None  # null for «под заказ» (on_order)
    qty_unit: str
    price: decimal.Decimal | None  # null for «под заказ» — shown as "по запросу"
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None
    country: str | None
    min_order_qty: decimal.Decimal | None
    description: str | None
    published_at: datetime.datetime | None
    files: list[OfferFileRef] = []
    # Dual-origin (R1 W5): who is behind the offer, regardless of seller/company.
    # Seller-origin offers keep these at their defaults (origin="seller",
    # display_name=seller.company_name, company_verified=False).
    origin: str = "seller"
    display_name: str | None = None
    company_verified: bool = False

    model_config = {"from_attributes": True}


class CatalogOfferOut(_CatalogOfferFields):
    """A public (approved) catalog offer. Seller block present only for seller-origin."""

    seller: CatalogSeller | None = None
    # True when the authenticated caller owns this offer. The catalog list excludes
    # own offers, so this is only ever True on the single-offer detail — the client
    # uses it to hide the "Request an offer" action (a seller can't buy from itself).
    is_own: bool = False


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
    qty_available: decimal.Decimal | None  # null for «под заказ» (on_order)
    qty_unit: str
    price: decimal.Decimal | None  # null for «под заказ» — shown as "по запросу"
    currency: str
    incoterms: PriceBasis
    warehouse_city: str | None
    country: str | None
    published_at: datetime.datetime | None
    files: list[OfferFileRef] = []
    # Dual-origin (R1 W5): public display + verified badge on the anonymous landing.
    origin: str = "seller"
    display_name: str | None = None
    company_verified: bool = False

    model_config = {"from_attributes": True}


class ModerationOfferOut(_CatalogOfferFields):
    """A pending offer for the dashboard moderation queue (adds status + seller/company)."""

    status: SellerOfferStatus
    created_at: datetime.datetime
    seller: ModerationSeller | None = None


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


class OfferRequestUpdate(OfferRequestCreate):
    """A buyer's revised inquiry — same shape + validation as create (full replacement).

    Editing an already-forwarded inquiry re-enters moderation and re-notifies the
    seller with the diff; a rejected inquiry cannot be edited (enforced in the service).
    """


class OfferBrief(BaseModel):
    """A minimal offer summary embedded in an inquiry (buyer + admin views)."""

    id: int
    product_id: int | None
    product_text: str | None
    grade_text: str | None
    price: decimal.Decimal | None  # null for «под заказ» — shown as "по запросу"
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
    edited_at: datetime.datetime | None = None
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


class AdminOfferRequestCompany(BaseModel):
    """Portal-company party block (R2 W4) — registered company + verified badge."""

    id: int
    name: str | None
    verified: bool


class AdminOfferRequestOut(BaseModel):
    """A pending inquiry for the dashboard review queue (both parties' contacts).

    Dual-origin (R2 W4): a TG buyer fills ``buyer``; a portal buyer fills
    ``buyer_company``. A TG seller fills ``seller``; a company-origin offer fills
    ``seller_company``. ``origin`` is the inquiry's origin ("client"/"company").
    """

    id: int
    status: OfferRequestStatus
    quantity: decimal.Decimal | None
    qty_unit: str
    target_price: decimal.Decimal | None
    currency: str | None
    message: str | None
    created_at: datetime.datetime
    origin: str = "client"
    offer: OfferBrief
    buyer: AdminOfferRequestBuyer | None = None
    buyer_company: AdminOfferRequestCompany | None = None
    seller: AdminOfferRequestSeller | None = None
    seller_company: AdminOfferRequestCompany | None = None
