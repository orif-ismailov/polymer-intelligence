"""
Chemical compliance (R5 / P5): substances, company licences, AI suggestions.

There is no machine-readable state registry of regulated chemistry in Uzbekistan
(`.planning/deal-lifecycle/INTEGRATIONS.md` §4) — the law of chemical safety is
still a draft and НРОХВ is empty. So `substances` IS our source of truth,
digitized from the official ПКМ lists and editable by an admin. That is an
architectural decision, not a stopgap.

Two consequences shape this module:

- **HS/ТН ВЭД is the legal identifier, CAS is secondary.** The Uzbek lists are
  written as names + HS codes; CAS shows up only in international SDS and is
  what the AI matcher recognizes. Hence `hs_code` NOT NULL, `cas` nullable UQ.
- **Regulation depends on concentration and volume.** Acetone is a Список IV
  precursor at ≥60% and ordinary solvent below it, with a ≤12 kg/year exemption.
  A bare "level" would over-block half of industrial chemistry, so the threshold
  and exemption travel with the substance.

The context extends the marketplace without changing its invariants: an offer
gains a substance link and a cached verdict; nothing about moderation changes.
"""

from __future__ import annotations

import datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.db import Base
from app.models.enums import LicenseStatus, RegulationLevel, RegulationRegime

if TYPE_CHECKING:
    from app.models.companies import Company


class Substance(Base):
    """One regulated (or explicitly free) substance in our own registry."""

    __tablename__ = "substances"
    __table_args__ = (
        Index("ix_substances_hs_code", "hs_code"),
        Index("ix_substances_level", "regulation_level"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: Stable slug — the natural key the idempotent seed upserts on, so a
    #: re-seed never duplicates a row and an operator edit is never overwritten
    #: by accident.
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name_ru: Mapped[str] = mapped_column(Text, nullable=False)
    name_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ТН ВЭД / HS. The primary LEGAL identifier — the official lists are keyed
    #: on it, so a registry row without one cannot be checked against an act.
    hs_code: Mapped[str] = mapped_column(Text, nullable=False)
    #: Secondary, international. Nullable because plenty of list entries are
    #: written as a group ("соли ...") that has no single CAS number.
    cas: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    hazard_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulation_level: Mapped[RegulationLevel] = mapped_column(
        PgEnum(RegulationLevel, name="regulation_level", create_type=False),
        nullable=False,
        default=RegulationLevel.free,
        server_default="free",
    )
    #: NULL for `free` substances — a regime is which act catches it, and a free
    #: substance is caught by none.
    regulation_regime: Mapped[RegulationRegime | None] = mapped_column(
        PgEnum(RegulationRegime, name="regulation_regime", create_type=False), nullable=True
    )
    #: Below this concentration the regime does not apply (Список IV: acetone
    #: 60%, hydrochloric acid 15%, …). NULL = the regime applies at any strength.
    threshold_concentration_pct: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    #: Annual volume below which the substance is out of control entirely
    #: (Список IV: ≤12 kg or litres per year), with its unit.
    exemption_annual_limit: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    exemption_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Which licence category the regime's licensor issues, when the regime
    #: distinguishes them. Checked against `company_licenses.category`.
    license_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Document kinds an offer must carry to publish — values of OfferFileKind
    #: (`sds`, `tds`, `coa`, `certificate`).
    required_docs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    #: Alternative names/spellings for search and AI matching (ru/uz/en/trade).
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    #: The act this row was digitized from, verbatim enough for a lawyer to
    #: re-check it ("ПКМ №330 от 12.11.2015, Список IV").
    source_act: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Which seed revision wrote the row; NULL for rows created by hand in the
    #: admin. Re-issuing a list = a new revision file, never an in-place edit.
    seed_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CompanyLicense(Base):
    """A licence a company holds, per REGIME (R1 ARCHITECTURE §CompanyLicense).

    The regime is the point. The four Uzbek regimes have four different
    licensors and four different document sets, so "this company holds a
    licence" is not a fact a publish gate can act on — an ecology certificate
    would otherwise unlock precursor trade.

    Evidence is a pointer to the R1 verification document the staff accepted;
    the licence row is the decision, so it outlives the document (SET NULL).
    """

    __tablename__ = "company_licenses"
    __table_args__ = (
        Index("ix_company_licenses_lookup", "company_id", "regime", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    regime: Mapped[RegulationRegime] = mapped_column(
        PgEnum(RegulationRegime, name="regulation_regime", create_type=False), nullable=False
    )
    #: Free text, matched case-insensitively against `substances.license_category`
    #: when the substance names one.
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    #: NULL = perpetual. Expiry is evaluated on read, never trusted to a nightly
    #: sweep — a gate that lets an expired licence through for a few hours is
    #: exactly the failure this table exists to prevent.
    expires_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[LicenseStatus] = mapped_column(
        PgEnum(LicenseStatus, name="license_status", create_type=False),
        nullable=False,
        default=LicenseStatus.pending_review,
        server_default="pending_review",
    )
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verification_documents.id", ondelete="SET NULL"), nullable=True
    )
    registered_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company] = relationship("Company")

    def is_active_on(self, day: datetime.date) -> bool:
        """True when this licence actually covers ``day``.

        Status alone is not enough: `active` with a past `expires_at` is an
        expired licence that nobody has swept yet.
        """
        if self.status != LicenseStatus.active or self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at >= day


class SubstanceSuggestion(Base):
    """One AI "this looks like X" hint and what the seller did with it (FR-C3).

    Append-only journal in the `parse_runs` spirit: the model and prompt version
    travel with the row, because a hint is only explainable if you know which
    prompt produced it.

    `accepted IS NULL` is a real state — the seller has not answered yet. A hint
    is NEVER written into the offer by itself.
    """

    __tablename__ = "substance_suggestions"
    __table_args__ = (
        Index("ix_substance_suggestions_company", "company_id", "id"),
        Index("ix_substance_suggestions_offer", "offer_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: NULL while the seller is still filling the form — the hint is asked for
    #: before the offer row exists.
    offer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seller_offers.id", ondelete="CASCADE"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: The registry row the candidate resolved to, or NULL when the model named
    #: something we do not carry (still journalled — that gap is the signal for
    #: extending the registry).
    substance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("substances.id", ondelete="SET NULL"), nullable=True
    )
    suggested_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_cas: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_hs_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_concentration_pct: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by_user_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
