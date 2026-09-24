"""
Contracts bounded context (R3 Stage B — the seed of the Deal Lifecycle domain).

A verified company creates a `Contract` from a `ContractTemplate` with another
verified company. Both sides sign with E-IMZO (each signature is an immutable
`SignatureEvidence` row, `purpose='contract'`, referenced from `ContractSignature`).
When both signatures are present the contract becomes `active`. The rendered PDF is
stored in S3 (`generated_document_path`) with its `document_sha256` for tamper
detection.

State machine + concurrency live in `app/services/contract_service.py` (transition
table; `SELECT … FOR UPDATE` on the contract row to avoid double-activation). This
module is only the schema.
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.db import Base
from app.models.enums import ContractStatus


class ContractTemplate(Base):
    """A bilingual document template + JSON Schema of its required variables.

    Despite the table name it backs more than contracts: `kind` discriminates, and
    the sample commitment letter (P7.a W8) is a row here too. Generalising the one
    column beat standing up a parallel table plus a second renderer — `render.py`
    is a pure `{{ key }}` substitution that neither knows nor cares what it is
    filling in.
    """

    __tablename__ = "contract_templates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('contract', 'sample_letter')",
            name="ck_contract_template_kind",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)           # e.g. SUPPLY_V1
    #: What this template renders. Existing rows are contracts — the default keeps
    #: every current caller (which never filters) correct without a data migration.
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="contract", server_default="contract"
    )
    name_ru: Mapped[str] = mapped_column(Text, nullable=False)
    name_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_storage_path: Mapped[str] = mapped_column(Text, nullable=False)           # S3 contracts/templates/…
    variables_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Contract(Base):
    """A contract between two verified companies (Deal Lifecycle seed)."""

    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "initiator_company_id <> counterparty_company_id",
            name="ck_contract_parties_distinct",
        ),
        CheckConstraint(
            "signing_provider IN ('eimzo', 'didox')",
            name="ck_contract_signing_provider",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=func.gen_random_uuid()
    )
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contract_templates.id"), nullable=False
    )
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    initiator_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False, index=True
    )
    counterparty_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False, index=True
    )
    offer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("seller_offers.id"), nullable=True
    )                                                                             # context link (optional)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    generated_document_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContractStatus] = mapped_column(
        PgEnum(ContractStatus, name="contract_status", create_type=False),
        nullable=False,
        default=ContractStatus.draft,
        server_default="draft",
    )
    #: Which rail carries the signatures (P7.a W2). `eimzo` — our own R3 flow, two
    #: `contract_signatures` rows over PKCS#7 we verified ourselves. `didox` — the
    #: legally significant artefact is the «Договор НК» inside Didox, which reaches
    #: my.soliq.uz, and our rendered PDF becomes a preview.
    #:
    #: FROZEN at creation, like `escrow_payments.mode`: once a `didox_documents`
    #: row exists the document is in a third-party system and in the roaming centre,
    #: and re-deciding which one is authoritative is not ours to do.
    #:
    #: Text + CHECK rather than a PG enum — a two-value provider list does not earn
    #: an ALTER TYPE, and `registry_snapshots.kind`/`source` set the precedent.
    signing_provider: Mapped[str] = mapped_column(
        Text, nullable=False, default="eimzo", server_default="eimzo"
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    declined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The company's saved set of terms this contract started from, if any. The
    #: values themselves are copied into `variables` — the preset may change or be
    #: archived later, and the contract must keep saying what was signed.
    term_preset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contract_term_presets.id", ondelete="SET NULL"), nullable=True
    )
    #: The commercial terms as columns, not only as strings inside `variables` —
    #: what the market analytics will read. Written by `service._sync_structured`
    #: on every create/edit; `variables` stays what the document is rendered from.
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoterms: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_window: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_total: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    signatures: Mapped[list[ContractSignature]] = relationship(
        "ContractSignature", back_populates="contract", cascade="all, delete-orphan"
    )


class ContractSignature(Base):
    """One company's E-IMZO signature on a contract (reuses signature_evidence)."""

    __tablename__ = "contract_signatures"
    __table_args__ = (
        UniqueConstraint("contract_id", "company_id", name="uq_contract_signature"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    signed_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    signature_evidence_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("signature_evidence.id"), nullable=False
    )
    signed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    contract: Mapped[Contract] = relationship("Contract", back_populates="signatures")


class ContractLine(Base):
    """One product line of a contract, as agreed — the analytics grain.

    Written from `variables` when the contract is created or edited, so it holds
    for BOTH rails; the tax classification (ИКПУ, package, VAT) is stamped on when
    a Didox document is built, because that is the first moment it is known.
    `qty`/`price` are NULL when the typed text is not a number — a zero would be
    a price nobody agreed to.
    """

    __tablename__ = "contract_lines"
    __table_args__ = (UniqueConstraint("contract_id", "ord_no", name="uq_contract_line_ord"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    ord_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    ikpu_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    ikpu_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: NULL means «без НДС» — a different statement from a 0 % rate.
    vat_rate: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)


class ContractTermPreset(Base):
    """A company's saved commercial terms — «шаблон условий».

    The legal text stays the platform's template; what a company repeats from one
    contract to the next is its terms (payment, delivery, Incoterms, special
    conditions), so that is what it saves. Choosing one fills the contract form;
    the contract then carries its own copy (see `Contract.term_preset_id`).
    """

    __tablename__ = "contract_term_presets"
    __table_args__ = (
        Index(
            "uq_contract_term_preset_name",
            "company_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
