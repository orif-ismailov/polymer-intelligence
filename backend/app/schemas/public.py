"""Response models for the anonymous marketplace storefront (/api/v1/public).

These are the only schemas in the codebase served to callers with no session at
all, so the field lists are a security boundary and not a convenience. Two rules
decide whether a field belongs here:

* **Would we print it on a business card?** Legal name, address, jurisdiction and
  confirmed roles are public register facts about a verified company. A contact
  person's phone number is not, and never appears -- reaching a supplier goes
  through the authenticated inquiry flow, which is also what makes the lead
  attributable.
* **Is it a moderation internal?** `status`, `moderation_note`, `moderated_by`,
  compliance verdicts and case data describe our review of a listing, not the
  listing. None of them are exposed.

`PublicOfferCard` extends `PublicFeaturedOffer` rather than `CatalogOfferOut`
precisely because the former already dropped the seller contact block for the
anonymous Telegram landing. Inheriting from the authenticated card and removing
fields would mean a field added upstream silently becomes public.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, Field

from app.schemas.marketplace import PublicFeaturedOffer


class PublicOfferCard(PublicFeaturedOffer):
    """A catalog offer as an anonymous visitor sees it in a grid."""

    lead_time_days: int | None = None
    min_order_qty: decimal.Decimal | None = None
    #: Confirmed roles of the selling company, driving the card's badge row.
    business_roles: list[str] = Field(default_factory=list)
    #: The two separate laboratory claims (FR-L5): a passport is attached, versus
    #: the analysis was run through the platform.
    has_lab_passport: bool = False
    lab_verified: bool = False
    samples_available: bool = False

    model_config = {"from_attributes": True}


class PublicOfferDetail(PublicOfferCard):
    """A single offer's public page: the card plus the product facts.

    Carries what a buyer needs to decide whether to ask, and stops there. The
    negotiable terms (sale mode, escrow readiness, sample pricing) stay behind
    the inquiry, which is the point at which we know who is asking.
    """

    description: str | None = None
    manufacturer: str | None = None
    key_properties: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    cas_number: str | None = None
    hs_code: str | None = None
    #: The selling company, when the offer came from one. NULL for the legacy
    #: Telegram-seller offers, which have no company to link to.
    seller_company_id: int | None = None
    seller_display_name: str | None = None


class PublicOfferListOut(BaseModel):
    """A page of the public catalog. `total` drives the grid's result count."""

    items: list[PublicOfferCard] = Field(default_factory=list)
    total: int = 0
    limit: int = 24
    offset: int = 0


class PublicLogisticsSnippet(BaseModel):
    """A carrier's questionnaire, as the public directory shows it.

    Every field is registration data the company published about itself — what
    it hauls, where, and with what fleet. Nothing here is a contact detail or a
    requisite: `tests/test_public_api.py` asserts the anonymous payload carries
    no way to reach a company off-platform, and this block must not become one.
    """

    city: str | None = None
    description: str | None = None
    services: list[str] = Field(default_factory=list)
    from_countries: list[str] = Field(default_factory=list)
    to_countries: list[str] = Field(default_factory=list)
    popular_routes: list[str] = Field(default_factory=list)
    cargo_types: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tariff_model: str | None = None
    years_experience: int | None = None
    projects_completed: int | None = None
    #: `{capability_key: url}` — only the keys that actually have a picture, so
    #: the client falls back to an icon for the rest rather than to a broken img.
    capability_images: dict[str, str] = Field(default_factory=dict)


class PublicReviewOut(BaseModel):
    """One published review, as a stranger reads it.

    The AUTHOR COMPANY is named; the person who typed it is not. `author_account_id`
    exists on the row for audit and must never reach this model — a review is a
    company's position, and naming the individual would also make every reviewer's
    identity scrapable.
    """

    id: int
    rating: int
    body: str | None = None
    author_company_name: str | None = None
    created_at: datetime.datetime


class PublicCompanyCard(BaseModel):
    """A verified company as it appears in a public directory."""

    id: int
    public_id: uuid.UUID
    legal_name: str | None = None
    short_name: str | None = None
    legal_address: str | None = None
    jurisdiction: str
    logo_url: str | None = None
    #: Hero image behind the logo. NULL for a company that never uploaded one.
    cover_url: str | None = None
    verified_at: datetime.datetime | None = None
    roles: list[str] = Field(default_factory=list)
    offer_count: int = 0
    #: Manufacturer profile snippet. Populated for any company that filled it in
    #: during registration, not only manufacturers -- a trading house that
    #: declared an ISO certificate should show it too.
    production_type: str | None = None
    main_products: str | None = None
    employees: int | None = None
    founded_year: int | None = None
    export_countries: list[str] = Field(default_factory=list)
    iso_certification: str | None = None
    #: Carrier questionnaire. NULL for a company that never filled one in, so the
    #: storefront omits the whole block rather than rendering an empty card —
    #: which is also why it is not flattened into the fields above the way the
    #: manufacturer snippet is.
    logistics: PublicLogisticsSnippet | None = None
    #: Published-review aggregate. `rating` is NULL — not 0 — for a company with
    #: no reviews: «нет отзывов» and «оценка 0» are different sentences, and the
    #: star line has to be able to tell them apart.
    rating: float | None = None
    review_count: int = 0


class PublicCompanyListOut(BaseModel):
    """A page of one directory."""

    items: list[PublicCompanyCard] = Field(default_factory=list)
    total: int = 0
    limit: int = 24
    offset: int = 0
    #: Echoed back so the client can title the page without re-deriving it.
    role: str


class PublicCompanyDetail(PublicCompanyCard):
    """A company's public profile plus its first page of listings."""

    registration_date: datetime.date | None = None
    legal_form: str | None = None
    offers: list[PublicOfferCard] = Field(default_factory=list)
    #: First page, inline rather than behind its own endpoint: the profile
    #: server-renders every tab panel, so a separate call would put a spinner in
    #: the crawled HTML. "Load more" is what a paginated endpoint would be for.
    reviews: list[PublicReviewOut] = Field(default_factory=list)


class PublicCategoryOut(BaseModel):
    """One category tile on the storefront."""

    product_id: int
    code: str
    label: str
    offer_count: int


class PublicFacetOut(BaseModel):
    """One option in a storefront filter dropdown."""

    value: str
    label: str
    offer_count: int = 0


class PublicStatsOut(BaseModel):
    """The hero strip's live figures plus the sidebar filters' option lists."""

    offer_count: int = 0
    company_count: int = 0
    country_count: int = 0
    #: Verified-company count per public directory role, keyed by role name.
    directory_counts: dict[str, int] = Field(default_factory=dict)
    #: Filter options aggregated from the approved catalog, busiest first, so a
    #: dropdown can never offer a value that matches nothing.
    countries: list[PublicFacetOut] = Field(default_factory=list)
    incoterms: list[PublicFacetOut] = Field(default_factory=list)
    companies: list[PublicFacetOut] = Field(default_factory=list)


class PublicQuoteOut(BaseModel):
    """One row of the market-price rail."""

    product_id: int
    code: str
    label: str
    price: decimal.Decimal
    currency: str
    unit: str
    observed_on: datetime.date
    #: Percent change against the previous observation, or None with no history.
    change_pct: decimal.Decimal | None = None


class PublicSitemapEntry(BaseModel):
    """One URL for the sitemap generator."""

    path: str
    lastmod: datetime.datetime | None = None


class PublicSitemapOut(BaseModel):
    """Everything the portal needs to write sitemap.xml.

    `truncated` is honest rather than decorative: the sitemap protocol caps a
    file at 50 000 URLs, and a generator that silently drops the overflow looks
    identical to one that covered everything.
    """

    entries: list[PublicSitemapEntry] = Field(default_factory=list)
    truncated: bool = False
