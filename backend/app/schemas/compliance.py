"""Compliance views: verdicts and company licences (P5 W3).

The verdict shape is shared by three surfaces — the seller's requirements panel,
the moderation card, and the 409 body a blocked approval returns — so it is
defined once here rather than assembled per router.
"""

from __future__ import annotations

import datetime
import decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer

from app.models.enums import LicenseStatus, RegulationLevel, RegulationRegime
from app.schemas.substance import SubstanceBrief


class MissingOut(BaseModel):
    """One unmet requirement. `detail` is a document kind, a regime, or the act."""

    kind: str
    detail: str | None = None


class ComplianceOut(BaseModel):
    """What publishing this offer requires right now."""

    ok: bool
    level: RegulationLevel
    regime: RegulationRegime | None = None
    exempt_reason: str | None = None
    missing: list[MissingOut] = Field(default_factory=list)
    substance: SubstanceBrief | None = None
    #: True when a failing verdict actually blocks. Lets the UI say "will be
    #: blocked when enforcement is switched on" instead of crying wolf.
    enforced: bool = False
    checked_at: datetime.datetime | None = None


class CompanyLicenseIn(BaseModel):
    """Staff registration of a licence a company holds."""

    regime: RegulationRegime
    category: str | None = Field(default=None, max_length=120)
    license_number: str | None = Field(default=None, max_length=120)
    issued_by: str | None = Field(default=None, max_length=300)
    issued_at: datetime.date | None = None
    expires_at: datetime.date | None = None
    #: The accepted R1 verification document this licence was read from.
    document_id: int | None = None
    note: str | None = Field(default=None, max_length=1000)


class LicenseRevokeIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CompanyLicenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    regime: RegulationRegime
    category: str | None = None
    license_number: str | None = None
    issued_by: str | None = None
    issued_at: datetime.date | None = None
    expires_at: datetime.date | None = None
    status: LicenseStatus
    document_id: int | None = None
    revoked_at: datetime.datetime | None = None
    revoke_reason: str | None = None
    note: str | None = None
    created_at: datetime.datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_active(self) -> bool:
        """Whether it covers today — status alone does not say (expiry is a date)."""
        if self.status != LicenseStatus.active or self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at >= datetime.date.today()


class OfferComplianceFields(BaseModel):
    """The compliance half of an offer payload (read side)."""

    substance_id: int | None = None
    cas_number: str | None = None
    hs_code: str | None = None
    declared_concentration_pct: decimal.Decimal | None = None
    compliance_level: RegulationLevel | None = None
    compliance_ok: bool | None = None
    compliance_missing: list[MissingOut] | None = None
    compliance_checked_at: datetime.datetime | None = None

    @field_serializer("declared_concentration_pct")
    def _concentration_as_string(self, value: decimal.Decimal | None) -> str | None:
        return None if value is None else str(value)
