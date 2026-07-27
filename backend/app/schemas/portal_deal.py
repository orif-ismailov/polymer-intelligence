"""Portal deal request/response schemas (R4 / P2 — T2.1).

Money and quantities cross the wire as strings, not floats: these are contract
terms, and a float round-trip is a wrong price.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from pydantic import BaseModel, Field, field_serializer


class PartyOut(BaseModel):
    """One side of a deal, as the other side sees it."""

    company_id: int
    name: str | None = None
    logo_url: str | None = None
    verified: bool = False
    roles: list[str] = Field(default_factory=list)


class TimelineEntryOut(BaseModel):
    id: int
    from_status: str | None = None
    to_status: str
    actor_kind: str
    reason: str | None = None
    created_at: datetime.datetime


class DealDocumentOut(BaseModel):
    id: int
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by_company_id: int
    uploaded_by_company_name: str | None = None
    revoked: bool
    revoked_reason: str | None = None
    created_at: datetime.datetime


class DealMessageOut(BaseModel):
    id: int
    body: str
    file_name: str | None = None
    has_file: bool = False
    author_account_id: int
    author_company_id: int
    author_company_name: str | None = None
    #: True when this side wrote it — drives left/right alignment in the room.
    mine: bool = False
    created_at: datetime.datetime


class DealMessagePageOut(BaseModel):
    items: list[DealMessageOut]
    #: Highest id in this page; feed it back as `after_id` on the next poll.
    last_id: int | None = None


class DealEscrowOut(BaseModel):
    """The money side of a deal, as both parties see it.

    Deliberately status + dates only. The buyer pays an invoice issued by the
    partner bank, so there is nothing here to act on and no account details to
    leak; the labels are rendered by the portal from `status`, never sent as
    prose from the server.
    """

    status: str
    amount: decimal.Decimal
    currency: str
    funded_at: datetime.datetime | None = None
    released_at: datetime.datetime | None = None
    refunded_at: datetime.datetime | None = None

    @field_serializer("amount")
    def _amount(self, value: decimal.Decimal) -> str:
        return f"{value:.2f}"


class DealSummaryOut(BaseModel):
    id: int
    public_id: uuid.UUID
    number: str
    status: str
    #: 'buyer' or 'seller' — which side the requesting company is on.
    role: str
    counterparty: PartyOut
    amount: decimal.Decimal | None = None
    currency: str
    contract_id: int | None = None
    #: True when this side has a move to make that is not cancel/dispute.
    needs_action: bool = False
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("amount")
    def _amount(self, value: decimal.Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class DealCountersOut(BaseModel):
    total: int
    needs_action: int
    active: int
    closed: int


class DealListOut(BaseModel):
    items: list[DealSummaryOut]
    counters: DealCountersOut


class DealDetailOut(DealSummaryOut):
    buyer: PartyOut
    seller: PartyOut
    request_id: int | None = None
    offer_id: int | None = None
    contract_status: str | None = None
    cancelled_reason: str | None = None
    timeline: list[TimelineEntryOut] = Field(default_factory=list)
    documents: list[DealDocumentOut] = Field(default_factory=list)
    #: Statuses THIS side may move to right now — the action bar reads this
    #: rather than re-deriving the state machine in TypeScript.
    available_transitions: list[str] = Field(default_factory=list)
    #: Null until the contract is signed and the invoice is raised — a deal in
    #: negotiation has no payment behind it yet.
    escrow: DealEscrowOut | None = None


class TransitionIn(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=1000)


class RevokeIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class RfqResponseIn(BaseModel):
    price: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    qty: decimal.Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    qty_unit: str = Field(default="MT", max_length=16)
    incoterms: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    comment: str | None = Field(default=None, max_length=2000)


class RfqResponseOut(BaseModel):
    id: int
    request_id: int
    company_id: int
    company_name: str | None = None
    company_verified: bool = False
    price: decimal.Decimal
    currency: str
    qty: decimal.Decimal
    qty_unit: str
    incoterms: str | None = None
    lead_time_days: int | None = None
    comment: str | None = None
    status: str
    deal_id: int | None = None
    created_at: datetime.datetime

    @field_serializer("price")
    def _price(self, value: decimal.Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("qty")
    def _qty(self, value: decimal.Decimal) -> str:
        return format(value.normalize(), "f")


class RfqResponseListOut(BaseModel):
    items: list[RfqResponseOut]


class MarketRequestOut(BaseModel):
    """A buyer RFQ as a supplier sees it — trade terms only.

    Deliberately omits `requests.company_name` / `contact_name` / `phone` /
    `legal_address`: the platform stays the intermediary until a deal is open.
    """

    id: int
    product: str | None = None
    grade: str | None = None
    volume: decimal.Decimal
    volume_unit: str
    incoterms: str
    destination_country: str
    port_or_city: str | None = None
    desired_date: datetime.date | None = None
    validity_days: int
    urgency: str
    required_docs: list[str] = Field(default_factory=list)
    created_at: datetime.datetime
    #: This company's own response to it, when there is one — so the UI shows
    #: "Responded" instead of a button the API would then reject.
    my_response_id: int | None = None
    my_response_status: str | None = None

    @field_serializer("volume")
    def _volume(self, value: decimal.Decimal) -> str:
        return format(value.normalize(), "f")


class MarketRequestListOut(BaseModel):
    items: list[MarketRequestOut]
