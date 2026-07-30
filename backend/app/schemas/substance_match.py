"""AI substance-match schemas (P5 W4 — T4.1).

`SubstanceMatchResult` is the instructor response model — the shape the LLM is
forced into. It carries identifiers only: the regulation level comes from our
own registry, never from the model.
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.substance import SubstanceBrief


class SubstanceMatchResult(BaseModel):
    """One candidate substance read out of an offer's free text."""

    name: str = Field(description="Common chemical name, Russian where one exists")
    cas: str | None = Field(default=None, description="CAS number, or null when unsure")
    hs_code: str | None = Field(default=None, description="HS / ТН ВЭД heading, or null")
    concentration_pct: float | None = Field(
        default=None, ge=0, le=100, description="Only when the text states it"
    )
    confidence: float = Field(ge=0, le=1)


class SuggestIn(BaseModel):
    """What the seller's form sends to ask for a hint."""

    text: str = Field(min_length=3, max_length=4000)
    #: Set once the offer exists, so the journal links the hint to the listing.
    offer_id: int | None = None


class SuggestionDecisionIn(BaseModel):
    """The seller's answer. False is a real answer, distinct from not answering."""

    accepted: bool


class SubstanceSuggestionOut(BaseModel):
    """A journalled hint plus the registry row it resolved to (if any)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    offer_id: int | None = None
    suggested_name: str | None = None
    suggested_cas: str | None = None
    suggested_hs_code: str | None = None
    suggested_concentration_pct: decimal.Decimal | None = None
    confidence: decimal.Decimal | None = None
    #: None when the model named something the registry does not carry — the
    #: seller can still type the identifiers by hand (FR-C2).
    substance: SubstanceBrief | None = None
    accepted: bool | None = None
    created_at: datetime.datetime

    @field_serializer("suggested_concentration_pct", "confidence")
    def _decimal_as_string(self, value: decimal.Decimal | None) -> str | None:
        return None if value is None else str(value)
