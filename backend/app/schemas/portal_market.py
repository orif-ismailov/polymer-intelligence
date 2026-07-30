"""Portal market read schemas (R2 W3 T3.1, extended in R4 / P4).

Twins of the webapp market surface. ``CatalogOfferOut`` IS the Mini App card and
its field set is pinned by a contract test; the portal card EXTENDS it rather
than adding to it, because `webapp/` is frozen and will never render P4's
badges — widening the shared class would drift a contract for no one's benefit.

The detail adds the caller company's own inquiries against the offer (the "my
relationship" block), reusing the buyer-facing ``OfferRequestOut`` so moderation
internals stay hidden, exactly as in the Mini App.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.enums import OfferSaleMode
from app.schemas.marketplace import (
    CatalogOfferOut,
    OfferRequestCreate,
    OfferRequestOut,
    OfferRequestUpdate,
)


class PortalMarketOfferOut(CatalogOfferOut):
    """The Mini App card plus what only the portal renders (P4 W1).

    `is_favorite` is per-ACCOUNT and resolved by the endpoint, so the heart is
    correct on first paint instead of after a second round trip.
    """

    lead_time_days: int | None = None
    sale_mode: OfferSaleMode | None = None
    accepts_rfq: bool = True
    accepts_contract: bool = False
    accepts_escrow: bool = False
    is_favorite: bool = False
    #: CONFIRMED business roles of the company behind the offer (P4 W2). Empty for
    #: seller-origin offers — there is no portal company to have confirmed any.
    business_roles: list[str] = []
    #: Laboratory (P6, FR-L1). Two different claims: a passport is attached
    #: (derived from the files) versus a platform lab order produced it. The
    #: market filters them separately for the same reason.
    has_lab_passport: bool = False
    lab_verified: bool = False
    #: Sample terms (P6, FR-L3) — a property of the listing, so the card can say
    #: "samples: 15 USD, ships in 3 days" before anyone asks.
    samples_available: bool = False
    sample_price: decimal.Decimal | None = None
    sample_dispatch_days: int | None = None
    #: Product facts the detail sheet paints (CAS / HS / maker / chip rows). The
    #: Mini App contract never carried them; the portal product page does.
    manufacturer: str | None = None
    key_properties: list[str] = []
    applications: list[str] = []
    cas_number: str | None = None
    hs_code: str | None = None

    @field_validator("key_properties", "applications", mode="before")
    @classmethod
    def _chips_none_to_empty(cls, value: object) -> object:
        # JSONB columns read back as NULL until the seller fills them; the sheet
        # always wants a list so the chips map never branches on "no chips yet".
        return value if value is not None else []


class PortalMarketOfferDetail(PortalMarketOfferOut):
    """A market offer detail card + the caller company's inquiries on this offer."""

    my_inquiries: list[OfferRequestOut] = []
    #: The selling COMPANY, so «Запросить контракт» can preselect a counterparty.
    #: `display_name` cannot do that job — it is `short_name or legal_name`, while
    #: the counterparty directory searches `legal_name`/`tax_id`, so a seller with
    #: a short name would never match its own listing. Both are NULL for
    #: seller-origin (Telegram) offers: there is no portal company to contract with.
    #: Detail-only on purpose — the list card is field-pinned against the Mini App.
    seller_company_id: int | None = None
    seller_legal_name: str | None = None


class PortalInquiryCreate(OfferRequestCreate):
    """Body for POST /portal/market/{offer_id}/inquiries — buyer acts as a company."""

    company_id: int


class PortalInquiryUpdate(OfferRequestUpdate):
    """Body for PATCH /portal/inquiries/{id} — the sending company revises it."""

    company_id: int


class PublicCompanyProfileOut(BaseModel):
    """Catalog-safe seller profile — strangers may read this; bank/docs/case may not.

    Only verified companies are returned by the endpoint. Confirmed roles only,
    same rule as the market card badges and the contract directory.
    """

    id: int
    public_id: uuid.UUID
    legal_name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    legal_address: str | None = None
    jurisdiction: str
    registration_date: datetime.date | None = None
    verified_at: datetime.datetime | None = None
    logo_url: str | None = None
    roles: list[str] = Field(default_factory=list)
    offer_count: int = 0
    #: First page of approved offers for the Products tab (caller may fetch more
    #: via GET /portal/market?seller_company_id=…).
    offers: list[PortalMarketOfferOut] = Field(default_factory=list)
