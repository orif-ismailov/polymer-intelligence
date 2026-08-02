"""Request/response models for the logistics-request surface."""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, Field, field_validator


class LogisticsRequestCreateIn(BaseModel):
    """«Быстрая заявка на логистику» — one screen, seven fields.

    `company_id` is the BUYER's acting company and travels in the body, matching
    `FactoryRfqCreateIn`: an account may belong to several companies, and which
    one is asking is a choice the client makes, not something the path can say.

    No contact block. The mockup has none and it is right not to — the sender is
    a member of a verified company, so the carrier already knows who is asking;
    the phone is snapshotted server-side from the account.
    """

    company_id: int
    cargo_name: str = Field(min_length=1, max_length=300)
    volume: decimal.Decimal = Field(gt=0)
    volume_unit: str = Field(default="MT", min_length=1, max_length=16)
    packaging_type: str | None = Field(default=None, max_length=100)
    special_requirements: str | None = Field(default=None, max_length=2000)
    from_country: str = Field(min_length=1, max_length=100)
    from_city: str | None = Field(default=None, max_length=200)
    to_country: str = Field(min_length=1, max_length=100)
    to_city: str | None = Field(default=None, max_length=200)

    @field_validator(
        "packaging_type", "special_requirements", "from_city", "to_city", mode="after"
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("cargo_name", "from_country", "to_country", "volume_unit", mode="after")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


class LogisticsRequestOut(BaseModel):
    """A request as either party reads it back."""

    id: int
    public_id: uuid.UUID
    number: str
    buyer_company_id: int
    logistics_company_id: int
    cargo_name: str
    volume: decimal.Decimal
    volume_unit: str
    packaging_type: str | None = None
    special_requirements: str | None = None
    from_country: str
    from_city: str | None = None
    to_country: str
    to_city: str | None = None
    contact_phone: str | None = None
    #: Plain `str`, not the enum — the wire contract is the value, and clients
    #: must not have to track a Python type to read it.
    status: str
    created_at: datetime.datetime
    #: Derived at read time from the FKs rather than stored: a company may be
    #: renamed, and a request should show what it is called now.
    buyer_name: str | None = None
    logistics_name: str | None = None


class LogisticsRequestListOut(BaseModel):
    items: list[LogisticsRequestOut] = Field(default_factory=list)
