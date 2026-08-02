"""Request/response models for the laboratory broadcast + its conversations."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, Field, field_validator


class LabRequestCreateIn(BaseModel):
    """The mockup's two sheets, «Новая заявка» + «Данные для заявки», in one body.

    `company_id` is the BUYER's acting company and travels in the body, matching
    every other company-scoped write: an account may belong to several, and which
    one is asking is the client's choice.

    No laboratory: the request is broadcast to every verified lab.
    """

    company_id: int
    # ── Что исследуем? ───────────────────────────────────────────────────────
    product_id: int | None = None
    product_text: str = Field(min_length=1, max_length=300)
    grade_text: str | None = Field(default=None, max_length=200)
    study_type: str | None = Field(default=None, max_length=100)
    methods: list[str] = Field(default_factory=list, max_length=48)
    sample_qty: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=2000)
    # ── Данные для заявки ────────────────────────────────────────────────────
    purpose: str | None = Field(default=None, max_length=300)
    is_urgent: bool = False
    desired_date: datetime.date | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=64)

    @field_validator("methods", mode="after")
    @classmethod
    def _clean_methods(cls, value: list[str]) -> list[str]:
        # `max_length=48` above is the bound; stripping cannot grow the list.
        return [item.strip() for item in value if item.strip()]

    @field_validator(
        "grade_text",
        "study_type",
        "sample_qty",
        "comment",
        "purpose",
        "contact_name",
        "contact_email",
        "contact_phone",
        mode="after",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("product_text", mode="after")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


class LabRequestOut(BaseModel):
    """A request as the buyer who filed it reads it back.

    Carries the contact block, so it must NOT be what the pool serves — see
    `LabPoolItemOut`.
    """

    id: int
    public_id: uuid.UUID
    number: str
    buyer_company_id: int
    product_id: int | None = None
    product_text: str
    grade_text: str | None = None
    study_type: str | None = None
    methods: list[str] = Field(default_factory=list)
    sample_qty: str | None = None
    comment: str | None = None
    purpose: str | None = None
    is_urgent: bool = False
    desired_date: datetime.date | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    #: Plain `str`, not the enum — the wire contract is the value.
    status: str
    created_at: datetime.datetime
    buyer_name: str | None = None
    #: How many laboratories have opened a conversation — the only signal that a
    #: broadcast landed anywhere.
    thread_count: int = 0


class LabPoolItemOut(BaseModel):
    """One open request as a LABORATORY sees it in the pool.

    A separate model rather than `LabRequestOut` minus three fields, for the same
    reason `LogisticsPoolItemOut` is: a lab gets the job, never the way to phone
    the buyer directly and take it off-platform. Inheriting and removing would
    mean a field added upstream silently becomes visible to every laboratory.
    """

    id: int
    number: str
    buyer_company_id: int
    buyer_name: str | None = None
    product_text: str
    grade_text: str | None = None
    study_type: str | None = None
    methods: list[str] = Field(default_factory=list)
    sample_qty: str | None = None
    comment: str | None = None
    purpose: str | None = None
    is_urgent: bool = False
    desired_date: datetime.date | None = None
    status: str
    created_at: datetime.datetime
    #: This laboratory's own thread, when it has already replied.
    my_thread_id: int | None = None


class LabRequestListOut(BaseModel):
    items: list[LabRequestOut] = Field(default_factory=list)


class LabPoolListOut(BaseModel):
    items: list[LabPoolItemOut] = Field(default_factory=list)


class LabThreadOpenIn(BaseModel):
    """The acting laboratory company."""

    company_id: int


class LabThreadOut(BaseModel):
    """One conversation, from whichever side is asking."""

    id: int
    lab_request_id: int
    request_number: str
    laboratory_company_id: int
    #: The OTHER party's name, resolved for the reader.
    counterparty_name: str | None = None
    #: `"buyer"` or `"laboratory"` — which side the reader is on.
    my_role: str
    product_text: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LabThreadListOut(BaseModel):
    items: list[LabThreadOut] = Field(default_factory=list)


class LabMessageOut(BaseModel):
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


class LabMessagePageOut(BaseModel):
    items: list[LabMessageOut] = Field(default_factory=list)
    #: Cursor for the client's poll; `None` when the page is empty.
    last_id: int | None = None
