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
