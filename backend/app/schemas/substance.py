"""Substance-registry schemas (P5 W2 — T2.2/T2.3/T2.4).

The registry is what a publish gate reasons over, so the write shape is
validated harder than a typical admin form: a row that cannot produce an
actionable verdict must not reach the table.
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.models.enums import OfferFileKind, RegulationLevel, RegulationRegime

#: Document kinds a substance may demand. A photo is not evidence of anything
#: chemical, so `image` is excluded even though it is a valid offer file kind.
COMPLIANCE_DOC_KINDS: frozenset[str] = frozenset(
    {OfferFileKind.sds, OfferFileKind.tds, OfferFileKind.coa, OfferFileKind.certificate}
)


class SubstanceIn(BaseModel):
    """Admin create/replace payload."""

    code: str = Field(min_length=2, max_length=64)
    name_ru: str = Field(min_length=1, max_length=300)
    name_uz: str | None = Field(default=None, max_length=300)
    name_en: str | None = Field(default=None, max_length=300)
    #: ТН ВЭД / HS — the legal identifier. Four digits is the shortest heading
    #: an official list uses.
    hs_code: str = Field(min_length=4, max_length=20)
    cas: str | None = Field(default=None, max_length=20)
    hazard_class: str | None = Field(default=None, max_length=50)
    regulation_level: RegulationLevel = RegulationLevel.free
    regulation_regime: RegulationRegime | None = None
    threshold_concentration_pct: decimal.Decimal | None = Field(default=None, ge=0, le=100)
    exemption_annual_limit: decimal.Decimal | None = Field(default=None, ge=0)
    exemption_unit: str | None = Field(default=None, max_length=20)
    license_category: str | None = Field(default=None, max_length=120)
    required_docs: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    source_act: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @model_validator(mode="after")
    def _a_verdict_must_be_actionable(self) -> SubstanceIn:
        """Reject registry rows that would produce a verdict nobody can satisfy."""
        if self.regulation_level != RegulationLevel.free and self.regulation_regime is None:
            raise ValueError(
                "regulation_regime is required for a regulated substance — the regime "
                "is which act catches it and whose licence satisfies it"
            )
        unknown = [kind for kind in self.required_docs if kind not in COMPLIANCE_DOC_KINDS]
        if unknown:
            raise ValueError(
                f"required_docs must be uploadable document kinds "
                f"({', '.join(sorted(COMPLIANCE_DOC_KINDS))}); got: {', '.join(unknown)}"
            )
        if self.regulation_level == RegulationLevel.docs_required and not self.required_docs:
            raise ValueError(
                "required_docs must name at least one document for a docs_required "
                "substance — otherwise the gate demands nothing"
            )
        return self


class SubstanceOut(BaseModel):
    """Full registry row (admin)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ru: str
    name_uz: str | None = None
    name_en: str | None = None
    hs_code: str
    cas: str | None = None
    hazard_class: str | None = None
    regulation_level: RegulationLevel
    regulation_regime: RegulationRegime | None = None
    threshold_concentration_pct: decimal.Decimal | None = None
    exemption_annual_limit: decimal.Decimal | None = None
    exemption_unit: str | None = None
    license_category: str | None = None
    required_docs: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    source_act: str | None = None
    #: Which seed revision owns the row; NULL after an operator edits it by hand.
    seed_revision: str | None = None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("threshold_concentration_pct", "exemption_annual_limit")
    def _decimal_as_string(self, value: decimal.Decimal | None) -> str | None:
        """Strings, not floats: a threshold of 60.00 must not arrive as 59.999…"""
        return None if value is None else str(value)


class SubstanceBrief(BaseModel):
    """Picker projection for the seller's offer form.

    Carries the regulation up front so a seller learns a licence is needed while
    choosing the substance, not from a 409 after filling in the whole form.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ru: str
    name_uz: str | None = None
    name_en: str | None = None
    hs_code: str
    cas: str | None = None
    regulation_level: RegulationLevel
    regulation_regime: RegulationRegime | None = None
    threshold_concentration_pct: decimal.Decimal | None = None
    required_docs: list[str] = Field(default_factory=list)

    @field_serializer("threshold_concentration_pct")
    def _threshold_as_string(self, value: decimal.Decimal | None) -> str | None:
        return None if value is None else str(value)
