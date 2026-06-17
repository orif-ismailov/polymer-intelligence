"""
Pydantic schemas for the Telegram Web App (/webapp/*) API surface.

Covers the request wizard (D-02 minimum-to-submit rule), the client profile,
and the read-side representations for requests, files, and status history.

D-02 minimum-to-submit: a RequestCreate is valid only when:
  - product_id is present (required int)
  - volume > 0 (required Decimal)
  - at least one of grade_text or polymer_type is non-empty

REQ-webapp-auth: These schemas carry no identity fields — identity is always
derived from the verified initData header (get_current_client dep), never from
the request body (T-03-06 equivalent).
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, field_validator, model_validator

from app.models.enums import PriceBasis, RequestStatus, Urgency


# ── Request creation ───────────────────────────────────────────────────────────

class RequestCreate(BaseModel):
    """Body for POST /webapp/requests.

    Enforces the D-02 minimum-to-submit rule:
      - product_id (required)
      - volume > 0 (required)
      - at least one of grade_text / polymer_type must be non-empty

    All other fields are optional with documented defaults.
    No identity fields — client identity comes from get_current_client dep (T-03-06).
    """

    product_id: int
    grade_text: str | None = None
    polymer_type: str | None = None
    volume: decimal.Decimal
    volume_unit: str = "MT"
    target_price: decimal.Decimal | None = None
    currency: str = "USD"
    incoterms: PriceBasis = PriceBasis.unknown
    destination_country: str = "UZ"
    port_or_city: str | None = None
    desired_date: datetime.date | None = None
    validity_days: int = 30
    urgency: Urgency = Urgency.medium
    comment: str | None = None

    @field_validator("volume")
    @classmethod
    def _volume_must_be_positive(cls, v: decimal.Decimal) -> decimal.Decimal:
        """Volume must be strictly positive (D-02)."""
        if v <= 0:
            raise ValueError("volume must be greater than 0")
        return v

    @model_validator(mode="after")
    def _d02_minimum_to_submit(self) -> "RequestCreate":
        """At least one of grade_text or polymer_type must be provided (D-02).

        The wizard Step 1 collects product + volume + (grade_text or polymer_type).
        A request with neither is considered incomplete and is rejected here at the
        schema layer rather than leaking through to the service.
        """
        grade_present = self.grade_text is not None and self.grade_text.strip() != ""
        polymer_present = self.polymer_type is not None and self.polymer_type.strip() != ""
        if not (grade_present or polymer_present):
            raise ValueError(
                "At least one of 'grade_text' or 'polymer_type' must be provided (D-02)"
            )
        return self


# ── Request read-side schemas ──────────────────────────────────────────────────

class RequestFileOut(BaseModel):
    """Attached file representation for API responses."""

    id: int
    file_name: str
    mime_type: str | None
    size_bytes: int | None

    model_config = {"from_attributes": True}


class StatusHistoryOut(BaseModel):
    """Single status-history entry for API responses."""

    from_status: RequestStatus | None
    to_status: RequestStatus
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class RequestOut(BaseModel):
    """Summary representation of a client request (list view)."""

    id: int
    number: str
    status: RequestStatus
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class RequestDetailOut(RequestOut):
    """Full representation of a client request (detail view).

    Extends RequestOut with all fields written by RequestCreate, attached files,
    and status history.  MR-03: added the 8 fields that were missing from the
    original schema (polymer_type, volume_unit, destination_country, port_or_city,
    desired_date, validity_days, urgency, comment).
    """

    product_id: int
    grade_text: str | None
    polymer_type: str | None
    volume: decimal.Decimal
    volume_unit: str
    target_price: decimal.Decimal | None
    currency: str
    incoterms: PriceBasis
    destination_country: str
    port_or_city: str | None
    desired_date: datetime.date | None
    validity_days: int
    urgency: Urgency
    comment: str | None
    files: list[RequestFileOut]
    history: list[StatusHistoryOut]

    model_config = {"from_attributes": True}


# ── Client profile schemas ─────────────────────────────────────────────────────

class ClientProfileOut(BaseModel):
    """Read representation of the authenticated client's profile."""

    id: int
    language: str
    company_name: str | None
    contact_name: str | None

    model_config = {"from_attributes": True}


class ClientProfilePatch(BaseModel):
    """Partial update body for PATCH /webapp/me.

    Only language, company_name, and contact_name are client-patchable.
    language is validated to 'ru' or 'uz' only.
    """

    language: str | None = None
    company_name: str | None = None
    contact_name: str | None = None

    @field_validator("language")
    @classmethod
    def _language_must_be_supported(cls, v: str | None) -> str | None:
        """Language must be 'ru' or 'uz' when provided."""
        if v is not None and v not in ("ru", "uz"):
            raise ValueError("language must be 'ru' or 'uz'")
        return v
