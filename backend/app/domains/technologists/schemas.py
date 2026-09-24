"""Request/response models for the technologist marketplace.

Three audiences, three shapes, never one model minus a field:

* `TechnologistCardOut` — the PUBLIC card (catalog, profile page, a factory's
  offer list). No contacts. Built from `published_snapshot`, never the live row.
* `TechnologistProfileOwnOut` — the expert's own editor, with contacts and the
  moderation state.
* `AdminTechnologistOut` — staff, who see both the live row and the snapshot.

A separate public model rather than "the own model with fields dropped" so that
a field added to the editor cannot silently become public — the same call
`LogisticsPoolItemOut` makes.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.technologists.catalog import (
    CapacityUnit,
    Currency,
    Industry,
    Language,
    Material,
    NeedType,
    Process,
    ProfileFormat,
    RequestFormat,
    Urgency,
)


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


# ── Profile ───────────────────────────────────────────────────────────────────


class TechnologistProfileIn(BaseModel):
    """The expert's editor. Everything optional — a draft is saved half-filled;
    completeness is checked at SUBMIT (`profiles.missing_fields`), not here."""

    full_name: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    projects_count: int | None = Field(default=None, ge=0, le=100_000)
    countries_count: int | None = Field(default=None, ge=0, le=250)
    bio: str | None = Field(default=None, max_length=4000)
    industries: list[Industry] = Field(default_factory=list, max_length=20)
    processes: list[Process] = Field(default_factory=list, max_length=20)
    materials: list[Material] = Field(default_factory=list, max_length=30)
    equipment_brands: list[str] = Field(default_factory=list, max_length=30)
    work_formats: list[ProfileFormat] = Field(default_factory=list, max_length=2)
    languages: list[Language] = Field(default_factory=list, max_length=10)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: str | None = Field(default=None, max_length=200)

    @field_validator(
        "full_name", "title", "country", "city", "bio", "contact_phone", "contact_email"
    )
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator(
        "industries", "processes", "materials", "work_formats", "languages", mode="after"
    )
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _dedupe(value)

    @field_validator("equipment_brands", mode="after")
    @classmethod
    def _brands(cls, value: list[str]) -> list[str]:
        cleaned = [b.strip()[:60] for b in value if b.strip()]
        return _dedupe(cleaned)


class TechnologistCardOut(BaseModel):
    """The public card. Contacts are absent by construction."""

    id: int
    full_name: str | None = None
    title: str | None = None
    country: str | None = None
    city: str | None = None
    photo_url: str | None = None
    years_experience: int | None = None
    projects_count: int | None = None
    countries_count: int | None = None
    bio: str | None = None
    industries: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    equipment_brands: list[str] = Field(default_factory=list)
    work_formats: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    rating_avg: decimal.Decimal | None = None
    rating_count: int = 0


class TechnologistCardListOut(BaseModel):
    items: list[TechnologistCardOut]
    total: int


class TechnologistProfileOwnOut(BaseModel):
    """The expert's own view: the live row, contacts, and where moderation stands."""

    id: int
    full_name: str | None = None
    title: str | None = None
    country: str | None = None
    city: str | None = None
    photo_url: str | None = None
    years_experience: int | None = None
    projects_count: int | None = None
    countries_count: int | None = None
    bio: str | None = None
    industries: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    equipment_brands: list[str] = Field(default_factory=list)
    work_formats: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    contact_phone: str | None = None
    contact_email: str | None = None
    status: str
    rejection_reason: str | None = None
    submitted_at: datetime.datetime | None = None
    reviewed_at: datetime.datetime | None = None
    #: True while the catalog shows (some approved version of) this profile.
    is_listed: bool
    #: The fields `submit` would refuse on — the editor highlights them.
    missing_fields: list[str] = Field(default_factory=list)
    rating_avg: decimal.Decimal | None = None
    rating_count: int = 0


class FacetsOut(BaseModel):
    industries: list[str]
    processes: list[str]
    materials: list[str]
    need_types: list[str]
    urgencies: list[str]
    request_formats: list[str]
    profile_formats: list[str]
    capacity_units: list[str]
    currencies: list[str]
    languages: list[str]


class AdminTechnologistOut(TechnologistProfileOwnOut):
    """Staff see the live row AND what the catalog currently serves."""

    user_account_id: int
    account_name: str | None = None
    account_phone: str | None = None
    published_snapshot: dict[str, Any] | None = None
    reviewed_by: int | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ModerationReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


# ── Requests ──────────────────────────────────────────────────────────────────


class TechRequestIn(BaseModel):
    """«Нужен технолог» — the ten questions of the brief, as one form."""

    need_type: NeedType
    process: Process
    equipment: str = Field(min_length=1, max_length=300)
    equipment_model: str | None = Field(default=None, max_length=300)
    product: str = Field(min_length=1, max_length=300)
    current_material: str | None = Field(default=None, max_length=200)
    target_material: str | None = Field(default=None, max_length=200)
    problem: str = Field(min_length=1, max_length=4000)
    capacity: decimal.Decimal | None = Field(default=None, gt=0)
    capacity_unit: CapacityUnit | None = None
    country: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    urgency: Urgency
    needed_by: datetime.date | None = None
    work_format: RequestFormat
    languages: list[Language] = Field(default_factory=list, max_length=10)
    budget_note: str | None = Field(default=None, max_length=500)

    @field_validator("equipment", "product", "problem", "country")
    @classmethod
    def _required(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator(
        "equipment_model", "current_material", "target_material", "city", "budget_note"
    )
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("languages", mode="after")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _dedupe(value)

    @model_validator(mode="after")
    def _consistent(self) -> TechRequestIn:
        if self.urgency == "date" and self.needed_by is None:
            raise ValueError("needed_by is required when urgency is 'date'")
        if self.urgency != "date":
            self.needed_by = None
        if self.capacity is not None and self.capacity_unit is None:
            raise ValueError("capacity_unit is required with capacity")
        if self.capacity is None:
            self.capacity_unit = None
        return self


class TechRequestOut(BaseModel):
    """A request as its own company reads it."""

    id: int
    number: str
    company_id: int
    need_type: str
    process: str
    equipment: str
    equipment_model: str | None = None
    product: str
    current_material: str | None = None
    target_material: str | None = None
    problem: str
    capacity: decimal.Decimal | None = None
    capacity_unit: str | None = None
    country: str
    city: str | None = None
    urgency: str
    needed_by: datetime.date | None = None
    work_format: str
    languages: list[str] = Field(default_factory=list)
    budget_note: str | None = None
    source: str
    status: str
    assigned_offer_id: int | None = None
    offer_count: int = 0
    created_at: datetime.datetime
    completed_at: datetime.datetime | None = None
    cancelled_at: datetime.datetime | None = None


class TechRequestListOut(BaseModel):
    items: list[TechRequestOut]


class FeedCompanyOut(BaseModel):
    id: int
    name: str | None = None


class TechFeedItemOut(BaseModel):
    """A request as an EXPERT reads it. A separate model, not the company's minus
    fields: `company` is null until a thread exists, and nothing here can carry
    the factory's contacts."""

    id: int
    number: str
    need_type: str
    process: str
    equipment: str
    equipment_model: str | None = None
    product: str
    current_material: str | None = None
    target_material: str | None = None
    problem: str
    capacity: decimal.Decimal | None = None
    capacity_unit: str | None = None
    country: str
    city: str | None = None
    urgency: str
    needed_by: datetime.date | None = None
    work_format: str
    languages: list[str] = Field(default_factory=list)
    budget_note: str | None = None
    status: str
    created_at: datetime.datetime
    company: FeedCompanyOut | None = None
    invited: bool = False
    my_offer: TechOfferOut | None = None
    my_thread_id: int | None = None
    #: The factory's contact — only once THIS expert's offer was accepted.
    contacts: ContactsOut | None = None


class TechFeedListOut(BaseModel):
    items: list[TechFeedItemOut]


class ContactsOut(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None


# ── Offers ────────────────────────────────────────────────────────────────────


class TechOfferIn(BaseModel):
    scope: str = Field(min_length=1, max_length=4000)
    price: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency = "USD"
    duration_days: int = Field(gt=0, le=365)
    work_format: RequestFormat

    @field_validator("scope")
    @classmethod
    def _required(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


class TechOfferOut(BaseModel):
    id: int
    request_id: int
    profile_id: int
    scope: str
    price: decimal.Decimal
    currency: str
    duration_days: int
    work_format: str
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CompanyOfferOut(TechOfferOut):
    """An offer as the FACTORY reads it: with the expert's public card, the
    thread to talk in, and — once accepted — the expert's contacts."""

    technologist: TechnologistCardOut
    thread_id: int | None = None
    contacts: ContactsOut | None = None


class CompanyOfferListOut(BaseModel):
    items: list[CompanyOfferOut]


class InviteIn(BaseModel):
    profile_id: int


class CompleteIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=4000)

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return _clean(value)


class TechReviewOut(BaseModel):
    id: int
    request_id: int
    profile_id: int
    rating: int
    text: str | None = None
    created_at: datetime.datetime


# ── Threads ───────────────────────────────────────────────────────────────────


class TechThreadOut(BaseModel):
    id: int
    request_id: int
    request_number: str
    profile_id: int
    #: `company` or `technologist` — which side the CALLER is on.
    my_side: str
    counterparty_name: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TechThreadListOut(BaseModel):
    items: list[TechThreadOut]


class TechMessageOut(BaseModel):
    """In the shape every `ThreadChat` endpoint returns, plus `mine`.

    `author_company_id` is kept for the shared component's fallback and is 0 on a
    technologist's line — an expert has no company. `mine` is what the client
    actually reads: which side is "me" is a server fact here, because one side of
    this thread is a person and not a company."""

    id: int
    author_kind: str
    author_company_id: int = 0
    mine: bool
    body: str
    has_file: bool
    file_name: str | None = None
    created_at: datetime.datetime


class TechMessagePageOut(BaseModel):
    items: list[TechMessageOut]
    last_id: int | None = None


TechFeedItemOut.model_rebuild()
