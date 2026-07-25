"""Portal market read schemas (R2 W3 T3.1).

Twins of the webapp market surface — the list reuses ``CatalogOfferOut`` verbatim
(field-set parity is pinned by a contract test), and the detail adds the caller
company's own inquiries against the offer (the "my relationship" block). The
inquiry view reuses the buyer-facing ``OfferRequestOut`` so moderation internals
stay hidden, exactly as in the Mini App.
"""

from __future__ import annotations

from app.schemas.marketplace import CatalogOfferOut, OfferRequestOut


class PortalMarketOfferDetail(CatalogOfferOut):
    """A market offer detail card + the caller company's inquiries on this offer."""

    my_inquiries: list[OfferRequestOut] = []
