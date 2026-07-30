"""Portal manufacturers directory + factory RFQ + chat schemas."""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, Field, field_validator


class ManufacturerCardOut(BaseModel):
    """One row on the manufacturers directory list."""

    id: int
    public_id: uuid.UUID
    legal_name: str | None = None
    short_name: str | None = None
    legal_address: str | None = None
    jurisdiction: str
    logo_url: str | None = None
    verified_at: datetime.datetime | None = None
    offer_count: int = 0
    #: Subset of `companies.manufacturer_profile` safe for the directory card.
    production_type: str | None = None
    main_products: str | None = None
    employees: int | None = None
    founded_year: int | None = None
    export_countries: list[str] = Field(default_factory=list)
    iso_certification: str | None = None


class ManufacturerListOut(BaseModel):
    items: list[ManufacturerCardOut]
    total: int
    limit: int
    offset: int


class FactoryRfqDocumentOut(BaseModel):
    id: int
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime.datetime


class FactoryRfqCreateIn(BaseModel):
    """Body for POST /portal/manufacturers/{id}/rfqs — buyer acts as a company."""

    company_id: int
    offer_id: int
    quantity: decimal.Decimal = Field(gt=0)
    qty_unit: str = Field(default="MT", max_length=16)
    target_price: decimal.Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    incoterms: str | None = Field(default=None, max_length=16)
    destination_port: str | None = Field(default=None, max_length=200)
    desired_delivery_date: datetime.date | None = None
    payment_method: str | None = Field(default=None, max_length=100)
    offer_validity: str | None = Field(default=None, max_length=100)
    performance_guarantee: str | None = Field(default=None, max_length=200)
    inspection_requirement: str | None = Field(default=None, max_length=200)
    additional_requirements: str | None = Field(default=None, max_length=2000)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_position: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=200)
    contact_phone: str = Field(min_length=1, max_length=40)
    contact_telegram: str | None = Field(default=None, max_length=100)

    @field_validator(
        "incoterms",
        "destination_port",
        "payment_method",
        "offer_validity",
        "performance_guarantee",
        "inspection_requirement",
        "additional_requirements",
        "contact_position",
        "contact_email",
        "contact_telegram",
        mode="after",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("qty_unit", "currency", mode="after")
    @classmethod
    def _strip_unit_currency(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("required")
        return trimmed

    @field_validator("contact_name", "contact_phone", mode="after")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("required")
        return trimmed


class FactoryRfqOut(BaseModel):
    id: int
    public_id: uuid.UUID
    number: str
    buyer_company_id: int
    manufacturer_company_id: int
    offer_id: int
    offer_title: str | None = None
    manufacturer_name: str | None = None
    quantity: decimal.Decimal
    qty_unit: str
    target_price: decimal.Decimal | None = None
    currency: str
    incoterms: str | None = None
    destination_port: str | None = None
    desired_delivery_date: datetime.date | None = None
    payment_method: str | None = None
    offer_validity: str | None = None
    performance_guarantee: str | None = None
    inspection_requirement: str | None = None
    additional_requirements: str | None = None
    contact_name: str
    contact_position: str | None = None
    contact_email: str | None = None
    contact_phone: str
    contact_telegram: str | None = None
    status: str
    documents: list[FactoryRfqDocumentOut] = Field(default_factory=list)
    created_at: datetime.datetime


class ManufacturerThreadOut(BaseModel):
    id: int
    buyer_company_id: int
    manufacturer_company_id: int
    counterparty_name: str | None = None
    my_role: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ManufacturerThreadOpenIn(BaseModel):
    company_id: int


class ManufacturerMessageOut(BaseModel):
    id: int
    thread_id: int
    author_account_id: int
    author_company_id: int
    body: str
    file_name: str | None = None
    has_file: bool = False
    created_at: datetime.datetime


class ManufacturerMessagePageOut(BaseModel):
    items: list[ManufacturerMessageOut]
    last_id: int | None = None
