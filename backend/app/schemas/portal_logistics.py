"""Request/response models for the logistics broadcast + its conversations."""

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

    No carrier: the request is broadcast to every verified logistics company.
    No contact block either — the mockup has none and it is right not to; the
    sender is a member of a verified company, so the phone is snapshotted
    server-side from the account.
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
    """A request as the buyer who filed it reads it back.

    Carries `contact_phone`, so it must NOT be what the pool serves — see
    `LogisticsPoolItemOut`.
    """

    id: int
    public_id: uuid.UUID
    number: str
    buyer_company_id: int
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
    #: Derived at read time from the FK rather than stored: a company may be
    #: renamed, and a request should show what it is called now.
    buyer_name: str | None = None
    #: How many carriers have opened a conversation. The buyer's list needs it;
    #: it is the only signal that a broadcast landed anywhere.
    thread_count: int = 0


class LogisticsPoolItemOut(BaseModel):
    """One open request as a CARRIER sees it in the pool.

    Deliberately a separate model rather than `LogisticsRequestOut` minus a
    field. `MarketRequestOut` makes the same call for polymer RFQs and for the
    same reason: a stranger to the deal gets the job, never the way to phone the
    buyer directly and take it off-platform. Inheriting and removing would mean a
    field added upstream silently becomes visible.
    """

    id: int
    number: str
    buyer_company_id: int
    buyer_name: str | None = None
    cargo_name: str
    volume: decimal.Decimal
    volume_unit: str
    packaging_type: str | None = None
    special_requirements: str | None = None
    from_country: str
    from_city: str | None = None
    to_country: str
    to_city: str | None = None
    status: str
    created_at: datetime.datetime
    #: This carrier's own thread, when it has already replied. Drives «Мои
    #: отклики» and lets the card open the conversation instead of starting one.
    my_thread_id: int | None = None


class LogisticsRequestListOut(BaseModel):
    items: list[LogisticsRequestOut] = Field(default_factory=list)


class LogisticsPoolListOut(BaseModel):
    items: list[LogisticsPoolItemOut] = Field(default_factory=list)


class LogisticsThreadOpenIn(BaseModel):
    """The acting carrier company. Matches `ManufacturerThreadOpenIn`."""

    company_id: int


class LogisticsThreadOut(BaseModel):
    """One conversation, from whichever side is asking."""

    id: int
    logistics_request_id: int
    request_number: str
    carrier_company_id: int
    #: The OTHER party's name, resolved for the reader — a buyer sees the
    #: carrier, a carrier sees the buyer.
    counterparty_name: str | None = None
    #: `"buyer"` or `"carrier"` — which side the reader is on.
    my_role: str
    cargo_name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LogisticsThreadListOut(BaseModel):
    items: list[LogisticsThreadOut] = Field(default_factory=list)


class LogisticsMessageOut(BaseModel):
    """One chat line.

    `has_file` rather than `file_storage_path`: the object key is internal, and
    the bytes come from a separate route that re-checks participation.
    """

    id: int
    author_company_id: int
    body: str
    has_file: bool = False
    file_name: str | None = None
    created_at: datetime.datetime


class LogisticsMessagePageOut(BaseModel):
    items: list[LogisticsMessageOut] = Field(default_factory=list)
    #: Cursor for the client's poll; `None` when the page is empty.
    last_id: int | None = None
