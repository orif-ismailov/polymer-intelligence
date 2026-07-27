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


class PortalMarketOfferDetail(PortalMarketOfferOut):
    """A market offer detail card + the caller company's inquiries on this offer."""

    my_inquiries: list[OfferRequestOut] = []


class PortalInquiryCreate(OfferRequestCreate):
    """Body for POST /portal/market/{offer_id}/inquiries — buyer acts as a company."""

    company_id: int


class PortalInquiryUpdate(OfferRequestUpdate):
    """Body for PATCH /portal/inquiries/{id} — the sending company revises it."""

    company_id: int
