"""
Lab-order schemas shared by the portal and the dashboard (P6 W2 — T2.3/T2.4).

A lab order is read by three audiences — the customer who raised it, the
operator working the queue, and the Trade Room panel — but only the operator's
view carries staff-side fields, so those stay inline in `admin_lab.py`. What is
here is the shape both sides agree on.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import LabOrderStatus


class LabOrderIn(BaseModel):
    """POST body — a customer asking for an analysis.

    Exactly one target: an order about both an offer and a deal would have two
    places to put its passport and no rule for choosing.
    """

    offer_id: int | None = None
    deal_id: int | None = None
    substance_id: int | None = None
    sample_volume: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> LabOrderIn:
        if (self.offer_id is None) == (self.deal_id is None):
            raise ValueError("exactly one of offer_id / deal_id is required")
        return self


class LabOrderOut(BaseModel):
    """A lab order as its customer sees it."""

    id: int
    number: str
    status: LabOrderStatus
    company_id: int
    offer_id: int | None = None
    deal_id: int | None = None
    substance_id: int | None = None
    sample_volume: str | None = None
    comment: str | None = None
    #: Named rather than an id: the customer's screen shows who is doing the work.
    lab_partner_name: str | None = None
    operator_note: str | None = None
    rejected_reason: str | None = None
    #: Where the passport ended up, so the client can link straight to it.
    result_offer_file_id: int | None = None
    result_deal_document_id: int | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class LabPartnerOut(BaseModel):
    """A laboratory in the directory (admin screen + assignment picker)."""

    id: int
    name: str
    contacts: dict[str, str] = Field(default_factory=dict)
    company_id: int | None = None
    note: str | None = None
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class LabPartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    contacts: dict[str, str] = Field(default_factory=dict)
    company_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


# ── Samples ───────────────────────────────────────────────────────────────────


class SampleRequestIn(BaseModel):
    """POST body — a buyer asking for a sample, acting as `company_id`."""

    company_id: int
    qty: str | None = Field(default=None, max_length=100)
    #: Prefilled by the portal from the company's legal address, but sent
    #: explicitly: the registered address and the warehouse that should receive
    #: the parcel are often different places.
    delivery_address: str = Field(min_length=1, max_length=500)


class SampleTransitionIn(BaseModel):
    """One body for every move — which party may make it is the server's call.

    Five hand-written verb routes would be five places to forget the role check;
    the machine is a table (`sample_service._ACTOR_RULES`), so the API is one
    door and the table decides.
    """

    company_id: int
    to_status: str
    reason: str | None = Field(default=None, max_length=1000)
    qty: str | None = Field(default=None, max_length=100)
    courier: str | None = Field(default=None, max_length=200)
    tracking_ref: str | None = Field(default=None, max_length=200)


class SampleRequestOut(BaseModel):
    """A sample request as one of its two parties sees it."""

    id: int
    offer_id: int
    offer_title: str | None = None
    status: str
    buyer_company_id: int
    seller_company_id: int
    #: The OTHER side's name, resolved for the caller — a list screen otherwise
    #: needs a company lookup per row.
    counterparty_name: str | None = None
    #: 'buyer' / 'seller' — which side the caller is on, so one component renders
    #: both tabs.
    my_role: str
    #: What the CALLER may do right now. Neither side is shown a move the API
    #: would refuse.
    available_transitions: list[str] = Field(default_factory=list)
    qty: str | None = None
    delivery_address: str
    courier: str | None = None
    tracking_ref: str | None = None
    decline_reason: str | None = None
    accepted_at: datetime.datetime | None = None
    sent_at: datetime.datetime | None = None
    received_at: datetime.datetime | None = None
    created_at: datetime.datetime
