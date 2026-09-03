"""Portal company/verification schemas (R1 W5 — T5.1/T5.2).

Client-facing views: bank numbers are masked (`****{last4}`), and case/check views
expose only user-safe fields (check_type, status, human requirement) — never a
reviewer identity, internal error, or waive metadata.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.compliance.schemas import MissingOut
from app.domains.compliance.substance_schemas import SubstanceBrief
from app.domains.marketplace.schemas import OfferFileRef
from app.domains.verification.schemas import CaseOut, DocumentOut
from app.models.enums import (
    OfferAvailability,
    OfferSaleMode,
    PriceBasis,
    RegulationLevel,
    SellerOfferStatus,
)

# ── Inputs ────────────────────────────────────────────────────────────────────


class CompanyCreateIn(BaseModel):
    jurisdiction: str = Field(default="UZ", max_length=32)
    tax_id: str = Field(max_length=32)


class ManufacturerProfileIn(BaseModel):
    """Production + buyer-requirement facts for a manufacturer registration.

    Stored as `companies.manufacturer_profile` JSONB. Other account types leave
    the column NULL; the wizard only sends this blob when the chosen type is
    manufacturer.
    """

    production_type: str | None = Field(default=None, max_length=200)
    main_products: str | None = Field(default=None, max_length=500)
    annual_capacity_tons: float | None = Field(default=None, ge=0, le=1_000_000_000)
    production_lines: int | None = Field(default=None, ge=0, le=10_000)
    employees: int | None = Field(default=None, ge=0, le=10_000_000)
    markets: list[str] = Field(default_factory=list, max_length=4)
    export_countries: list[str] = Field(default_factory=list, max_length=64)
    founded_year: int | None = Field(default=None, ge=1800, le=2100)
    iso_certification: str | None = Field(default=None, max_length=200)
    moq_tons: float | None = Field(default=None, ge=0, le=1_000_000_000)
    min_annual_volume_tons: float | None = Field(default=None, ge=0, le=1_000_000_000)
    financial_requirements: dict[str, bool] = Field(default_factory=dict)
    additional_requirements: list[str] = Field(default_factory=list, max_length=32)
    additional_other: str | None = Field(default=None, max_length=500)

    @field_validator("markets", "export_countries", "additional_requirements", mode="after")
    @classmethod
    def _clean_string_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:64]

    @field_validator(
        "production_type",
        "main_products",
        "iso_certification",
        "additional_other",
        mode="after",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class LogisticsProfileIn(BaseModel):
    """Services / geography / cargo / tariff facts for a logistics registration.

    Stored as `companies.logistics_profile` JSONB. Other account types leave the
    column NULL; the wizard only sends this blob for the logistics account type
    (`docs/new-design/logist_reg_flow.jpeg`).
    """

    city: str | None = Field(default=None, max_length=200)
    services: list[str] = Field(default_factory=list, max_length=32)
    from_countries: list[str] = Field(default_factory=list, max_length=64)
    to_countries: list[str] = Field(default_factory=list, max_length=64)
    popular_routes: list[str] = Field(default_factory=list, max_length=64)
    cargo_types: list[str] = Field(default_factory=list, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    tariff_model: str | None = Field(default=None, max_length=100)
    #: Storefront copy — the blurb and the two figures the public profile prints
    #: as «Опыт работы» / «Реализованных проектов». Bounded so a typo cannot
    #: render as «Опыт работы: 99999 лет»; the read side caps them again, since
    #: the column is untyped JSONB that predates these keys.
    description: str | None = Field(default=None, max_length=4000)
    years_experience: int | None = Field(default=None, ge=0, le=200)
    projects_completed: int | None = Field(default=None, ge=0, le=10_000_000)
    #: `{capability_key: media_id}` from `POST /companies/{id}/media`. The JSONB
    #: is the ordering authority; media rows are just bytes with an owner.
    capability_images: dict[str, int] = Field(default_factory=dict)

    @field_validator(
        "services",
        "from_countries",
        "to_countries",
        "popular_routes",
        "cargo_types",
        "capabilities",
        mode="after",
    )
    @classmethod
    def _clean_string_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:64]

    @field_validator("city", "tariff_model", "description", mode="after")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class CompanyMediaOut(BaseModel):
    """An uploaded image: its id and the root-relative URL to its bytes.

    The storage key is never returned — it is an object-store path, and the only
    thing a client needs is a `src`.
    """

    id: int
    url: str
    mime_type: str
    size_bytes: int


class CompanyReviewIn(BaseModel):
    """A company's rating of a counterparty.

    `company_id` is the AUTHOR's acting company, in the body for the same reason
    every other company-scoped write puts it there: an account may belong to
    several, and which one is speaking is the client's choice.
    """

    company_id: int
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=4000)

    @field_validator("body", mode="after")
    @classmethod
    def _strip_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class CompanyReviewOut(BaseModel):
    """The author's own review, read back after writing it."""

    id: int
    company_id: int
    author_company_id: int
    rating: int
    body: str | None = None
    status: str
    created_at: datetime.datetime


class PublicProfileUpdateIn(BaseModel):
    """Storefront copy a company may edit after it is verified.

    Read with `exclude_unset=True`, never `exclude_none=True`: every field on
    these has a default, so a PATCH carrying only `description` would otherwise
    arrive with `services=[]` and wipe the list the registration wizard
    collected.

    Both halves optional — a company sends the one matching its role.
    """

    logistics: LogisticsProfileIn | None = None
    laboratory: LaboratoryProfileIn | None = None


class LaboratoryProfileIn(BaseModel):
    """Contact / description facts for a laboratory registration.

    Stored as `companies.laboratory_profile` JSONB. Other account types leave the
    column NULL; the wizard only sends this blob for the laboratory account type
    (`docs/new-design/labaratory_reg_flow.jpeg` — «Основная информация»).
    """

    city: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    #: Storefront copy — the chips and the three stat tiles on the public sheet.
    #: Keys, not labels: `accreditations` and `methods` resolve through the same
    #: i18n tree the registration wizard writes them from.
    accreditations: list[str] = Field(default_factory=list, max_length=16)
    methods: list[str] = Field(default_factory=list, max_length=48)
    years_experience: int | None = Field(default=None, ge=0, le=200)
    studies_completed: int | None = Field(default=None, ge=0, le=100_000_000)
    avg_turnaround_days: int | None = Field(default=None, ge=0, le=365)

    @field_validator("accreditations", "methods", mode="after")
    @classmethod
    def _clean_lab_lists(cls, value: list[str]) -> list[str]:
        # No slice: `max_length` above is the bound, and stripping cannot grow a
        # list — a second cap here would only look like one.
        return [item.strip() for item in value if item.strip()]

    @field_validator("city", "website", "email", "phone", "description", mode="after")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class CompanyProfileUpdateIn(BaseModel):
    """Declared profile fields.

    Every string is length-capped and blank-rejected here rather than trusted from
    the client: these columns are unbounded `text`, so the API previously accepted
    a 100 000-character `legal_name`, a whitespace-only name, and a registration
    date in the year 9999 — all of which the wizard forbids but no API client had
    to. `legal_form` is deliberately NOT constrained to the wizard's six options:
    it is free text on the server, predates that select, and older/E-IMZO-filled
    rows carry values outside the list (see StepDetails' legalFormOptions).
    """

    legal_name: str | None = Field(default=None, max_length=300)
    short_name: str | None = Field(default=None, max_length=200)
    legal_form: str | None = Field(default=None, max_length=100)
    legal_address: str | None = Field(default=None, max_length=500)
    actual_address: str | None = Field(default=None, max_length=500)
    registration_number: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=200)
    #: Date on the registration certificate — collected by the wizard's
    #: «Дата регистрации компании» field and shown back on the company card.
    registration_date: datetime.date | None = None
    manufacturer_profile: ManufacturerProfileIn | None = None
    logistics_profile: LogisticsProfileIn | None = None
    laboratory_profile: LaboratoryProfileIn | None = None

    @field_validator(
        "legal_name",
        "short_name",
        "legal_form",
        "legal_address",
        "actual_address",
        "registration_number",
        "director_name",
        mode="after",
    )
    @classmethod
    def _strip_non_blank(cls, value: str | None) -> str | None:
        """Trim, and treat a whitespace-only value as absent rather than storing it."""
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("registration_date", mode="after")
    @classmethod
    def _not_in_the_future(cls, value: datetime.date | None) -> datetime.date | None:
        """A company cannot have been registered tomorrow (the wizard also caps this)."""
        if value is not None and value > datetime.datetime.now(datetime.UTC).date():
            raise ValueError("registration_date cannot be in the future")
        return value


class RolesUpdateIn(BaseModel):
    roles: list[str]


class BankAccountIn(BaseModel):
    bank_mfo: str
    account_number: str
    bank_name: str | None = None
    currency: str = "UZS"


# ── Company views ─────────────────────────────────────────────────────────────
#
# CheckOut/CaseOut/DocumentOut moved to app/domains/verification/schemas.py; the
# company views below still embed them, so they are imported rather than redefined.


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
    cover_url: str | None = None
    #: CONFIRMED business roles, as plain strings. On the summary and not just
    #: the detail because the cabinet branches on them — `/cabinet/requests`
    #: shows a carrier the broadcast pool instead of its own (always empty)
    #: purchase requests — and `useActiveCompany()` is backed by the summary
    #: list, so without this every such branch costs a second round-trip.
    #:
    #: NOT called `roles`: `CompanyDetailOut.roles` is a list of
    #: `{role, status}` objects, and one name for two shapes is how a client
    #: ends up reading `.role` off a string.
    confirmed_roles: list[str] = Field(default_factory=list)
    #: NON-REVOKED (declared or confirmed) roles, as plain strings — what the
    #: company registered as. The cabinet's role-based show/hide keys off this,
    #: not `confirmed_roles`, so a draft company already gets the right cabinet
    #: shape before staff have vouched for it. Same not-`roles` naming rule as
    #: above.
    declared_roles: list[str] = Field(default_factory=list)
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
    actual_address: str | None = None
    registration_number: str | None = None
    director_name: str | None = None
    registration_date: datetime.date | None = None
    manufacturer_profile: dict[str, object] | None = None
    logistics_profile: dict[str, object] | None = None
    laboratory_profile: dict[str, object] | None = None
    status: str
    identity_locked: bool = False
    verified_at: datetime.datetime | None = None
    reverification_due_at: datetime.datetime | None = None
    #: See CompanySummaryOut.logo_url — presigned per response, never stored.
    logo_url: str | None = None
    cover_url: str | None = None
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
    # ── Product facts (migration 0030) ────────────────────────────────────────
    #: Who made the goods, and the two chip rows on the product sheet. Capped in
    #: count as well as length: the sheet renders them as pills, and a hundred of
    #: them is not a spec, it is a paste.
    manufacturer: str | None = Field(default=None, max_length=200)
    key_properties: list[str] = Field(default_factory=list, max_length=12)
    applications: list[str] = Field(default_factory=list, max_length=12)
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
    # ── Samples (P6) ──────────────────────────────────────────────────────────
    #: Sample terms are a property of the LISTING — the same for every buyer who
    #: asks — so they live here rather than on each request. A NULL price with
    #: samples available means free.
    samples_available: bool = False
    sample_price: decimal.Decimal | None = Field(default=None, ge=0)
    #: Require the buyer to e-sign a commitment letter before this request reaches
    #: the seller. Per-offer because the paperwork should be proportional to what
    #: is being given away: 200 g of granulate warrants none, 25 kg does.
    sample_letter_required: bool = False
    #: The seller's own "if the material does not suit the buyer" clause. Rendered
    #: into the letter verbatim and snapshotted onto the request when the buyer
    #: signs — the platform does not write this consequence for two other
    #: businesses, which is why the validator below refuses to default it.
    sample_letter_terms: str | None = Field(default=None, max_length=4000)

    # ── ИКПУ (P7.a W9) — the tax classification of these goods ────────────
    #: Chosen ONCE here and reused by every договор and ЭСФ this offer backs.
    #: NULL is a permanent, legitimate state: back-filling would mean inventing a
    #: tax classification for someone else's goods, so an offer without a code
    #: simply cannot back a Didox document and says so at contract time.
    ikpu_code: str | None = Field(default=None, max_length=32)
    ikpu_name: str | None = Field(default=None, max_length=500)
    ikpu_package_code: str | None = Field(default=None, max_length=32)
    ikpu_package_name: str | None = Field(default=None, max_length=200)
    ikpu_origin: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="after")
    def _ikpu_is_all_or_nothing(self) -> CompanyOfferIn:
        """A half-filled ИКПУ is worse than none.

        It builds a document Didox rejects at SEND time — after the seller has
        loaded a key and typed its password — so it fails here instead. The DB
        CHECK says the same thing; this is the copy that produces a form error.
        """
        if self.ikpu_code and not (self.ikpu_package_code and self.ikpu_origin):
            raise ValueError("ikpu_package_code and ikpu_origin are required with an ikpu_code")
        return self

    @model_validator(mode="after")
    def _letter_needs_terms(self) -> CompanyOfferIn:
        """A required letter must say what happens if the sample does not fit.

        Defaulting the clause would mean the platform inventing a commercial
        consequence between two other companies, and an empty one would put a
        blank section into a document the buyer signs. Both are worse than a form
        error, so this is a hard rule rather than a hint.
        """
        if self.sample_letter_required and not (self.sample_letter_terms or "").strip():
            raise ValueError("sample_letter_terms is required when a letter is demanded")
        return self
    sample_dispatch_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("key_properties", "applications", mode="after")
    @classmethod
    def _clean_chips(cls, value: list[str]) -> list[str]:
        """Trim, drop blanks, cap each chip — a pill is a phrase, not a paragraph."""
        cleaned = [chip.strip()[:80] for chip in value if chip.strip()]
        return cleaned

    @model_validator(mode="after")
    def _sample_terms_need_samples(self) -> CompanyOfferIn:
        """A price or a dispatch time for a sample nobody can order is a card
        that promises something the seller did not offer."""
        if not self.samples_available and (
            self.sample_price is not None or self.sample_dispatch_days is not None
        ):
            raise ValueError("sample terms require samples_available")
        return self

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
    #: Product facts (0030). NULL columns read back as empty lists so the client
    #: never has to branch on "no chips yet" versus "chips cleared".
    manufacturer: str | None = None
    key_properties: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
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
    #: Samples + laboratory (P6). `has_lab_passport` is derived from the files,
    #: `lab_verified` is the flag only a finished platform lab order sets.
    samples_available: bool = False
    sample_price: decimal.Decimal | None = None
    sample_dispatch_days: int | None = None
    has_lab_passport: bool = False
    lab_verified: bool = False
    #: The commitment letter the seller may demand before a sample ships (W8) and
    #: the tax classification of the goods (W9).
    #:
    #: These are READ-BACK fields, and that is load-bearing: the offer form
    #: hydrates from this schema and PUTs the whole draft back, so a field missing
    #: here returns as `None` and overwrites the stored value. Omitting them meant
    #: any edit — a fixed typo in the description — silently erased the ИКПУ and
    #: the letter terms, and the seller only found out at contract time.
    sample_letter_required: bool = False
    sample_letter_terms: str | None = None
    ikpu_code: str | None = None
    ikpu_name: str | None = None
    ikpu_package_code: str | None = None
    ikpu_package_name: str | None = None
    ikpu_origin: int | None = None
    moderation_note: str | None = None
    created_at: datetime.datetime
    #: Attached files in upload order (photos + documents), so the seller's own
    #: screens can render previews on a draft too — not just the public catalog.
    files: list[OfferFileRef] = Field(default_factory=list)
    #: The first photo. None when the offer has no photos (renders a placeholder).
    cover_file_id: int | None = None

    @field_validator("key_properties", "applications", mode="before")
    @classmethod
    def _chips_never_null(cls, value: list[str] | None) -> list[str]:
        """The columns are nullable (0030 backfilled nothing), and a client that
        has to tell `null` from `[]` will eventually get it wrong."""
        return value or []


class CompanyRegistryDataOut(BaseModel):
    """What the state registry says about a STIR, shaped for the wizard's fields.

    Deliberately NOT the whole provider record. Any portal account can look up
    any STIR, so this carries only what a counterparty reads off an invoice —
    requisites plus the director's name. The director's ПИНФЛ and tax id, and the
    accountant's name, are personal identifiers and stop at the service layer.
    """

    tax_id: str
    legal_name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    legal_address: str | None = None
    registration_date: datetime.date | None = None
    director_name: str | None = None
    oked: str | None = None
    bank_mfo: str | None = None
    bank_account: str | None = None
    vat_registered: bool = False
    vat_certificate_no: str | None = None
    #: Normalized (`active`/`liquidated`/`suspended`/`unknown`) + the registry's
    #: own wording, which is what a verifier actually wants to read.
    registry_status: str = "unknown"
    registry_status_text: str | None = None


class CompanyLookupOut(BaseModel):
    """Envelope for the prefill lookup.

    `found=False` is an ordinary answer, not an error: Didox reports "no such
    company" as a 200 with an empty body, and the form must stay manual rather
    than fill itself with nulls.
    """

    found: bool
    company: CompanyRegistryDataOut | None = None


class DirectoryCompanyOut(BaseModel):
    """One row of the verified-company picker (`GET /portal/companies/directory`).

    Moved here from the contracts schemas in P4: the query behind it is a pure
    companies query and never touched a contract table.
    """

    id: int
    public_id: uuid.UUID
    legal_name: str | None = None
    tax_id: str
    roles: list[str] = Field(default_factory=list)
    verified: bool = True
