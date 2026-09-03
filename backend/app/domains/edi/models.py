"""Didox rail: `didox_documents` + `didox_companies` (P7.a Stage 2 — W2).

One table holds BOTH document types. The ЭСФ has no `contracts` row to hang off,
and the lifecycle is byte-identical either way — create, sign, Didox's own status
ladder, one archive fetched at `signed`, and the two terminal surprises (`4` отказ,
`50` аннулирован НК) that are staff alerts rather than state transitions. Two tables
would mean two writers, two archive disciplines and two status-50 handlers.

`status` is a smallint carrying Didox's number verbatim, not a PG enum: their ladder
is theirs to extend (it already forks for ТТН and доверенность), and there is no
invariant of ours for an enum to protect.

The archive columns live HERE rather than on `contracts` — a deliberate deviation from
.planning/deal-lifecycle/P7-PROVIDERS-LIVE.md §P7.a, which predates the ЭСФ being in
scope. The decision it records still holds: the provider's archive is a SECOND artefact
with its own hash, and it must never overwrite `contracts.generated_document_path` /
`document_sha256`, which describe our own rendered preview.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.db import Base

#: Didox document types this rail creates. `000` («Произвольный документ») is
#: deliberately absent: it never enters roaming, so it cannot stand in for a договор.
DOC_TYPE_CONTRACT = "007"
DOC_TYPE_FACTURE = "002"

#: Didox's own status ladder for these two types (reference/09-catalogs.md §6).
STATUS_DRAFT = 0
STATUS_AWAITING_PARTNER = 1
STATUS_AWAITING_US = 2
STATUS_SIGNED = 3
STATUS_REJECTED = 4
STATUS_DELETED = 5
STATUS_DRAFT_DELETED = 55
STATUS_ANNULLED_BY_TAX = 50

#: Statuses in which a document no longer occupies its subject's slot.
_DEAD_STATUSES = (STATUS_DELETED, STATUS_DRAFT_DELETED)


class DidoxDocument(Base):
    """One document we created in Didox, of either type."""

    __tablename__ = "didox_documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('007', '002')",
            name="ck_didox_document_type",
        ),
        CheckConstraint(
            "subject_kind IN ('contract', 'deal')",
            name="ck_didox_document_subject_kind",
        ),
        # `didox_id` arrives one round trip AFTER the row is committed, so it is
        # nullable and unique only when set. That gap is the whole recovery story:
        # a create Didox accepted and we timed out on leaves a row carrying our
        # `number`, findable by ContractNo, instead of nothing at all.
        Index(
            "uq_didox_documents_didox_id",
            "didox_id",
            unique=True,
            postgresql_where=text("didox_id IS NOT NULL"),
        ),
        # One LIVE document of a type per subject — same discipline as
        # `uq_sample_request_active`: deleting a draft frees the slot, and a
        # document that reached the roaming centre never does.
        Index(
            "uq_didox_documents_subject",
            "subject_kind",
            "subject_id",
            "doc_type",
            unique=True,
            postgresql_where=text("status NOT IN (5, 55)"),
        ),
        Index("ix_didox_documents_poll", "status", "status_synced_at"),
        Index("ix_didox_documents_deal", "deal_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    #: Didox's hex `_id` from create — the handle every later call takes.
    didox_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Didox's INTEGER `contractid`, which is a DIFFERENT identifier from `_id`
    #: and is what `GET /v1/documents/contract/{contractId}/info` takes. Kept
    #: separately because which one the ЭСФ's `didoxcontractid` wants is decided
    #: by the live contour, not by the docs.
    didox_contract_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Polymorphic owner — 'contract' → contracts.id, 'deal' → deals.id. No FK:
    #: a single column cannot reference two tables, and the alternative (two
    #: nullable FKs plus a CHECK) buys nothing the service does not already check.
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Denormalised so the deal screen and the poller can join without knowing
    #: which subject kind a row is.
    deal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("deals.id", ondelete="SET NULL"), nullable=True
    )

    #: Whose `user-key` created it — a document is attributable to one company.
    owner_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    partner_company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=True
    )

    #: Our ContractNo / FacturaNo, allocated BEFORE the POST so a retried create
    #: reuses the number rather than burning a second one out of the seller's book.
    number: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    #: Didox's ladder, verbatim. `0` is what a row starts as, before we have sent
    #: anything at all — which is also what an un-created row looks like.
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=STATUS_DRAFT, server_default="0"
    )
    status_synced_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: The PascalCase body we POSTed, kept verbatim. It is evidence of what we
    #: asserted — including the VAT registration status read on that date, which
    #: is date-sensitive and must never be re-derived after the fact.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    #: The provider's evidence pack (ZIP: signatures + PDF + JSON), fetched once
    #: on the transition to `signed`. A SECOND artefact with its own hash — it
    #: does not replace our rendered preview, which stays on `contracts`.
    provider_archive_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_archive_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_live(self) -> bool:
        """False once the document is deleted — i.e. it no longer holds its slot."""
        return self.status not in _DEAD_STATUSES


class DidoxCompany(Base):
    """Whether a company can send documents through Didox at all.

    Two facts, both about a third-party account and both durable:

      * `signup_at`      — the company exists in Didox (`POST /v1/auth/signup`).
      * `offer_signed_at` — it has signed Didox's public offer, WITHOUT which the
        first document send fails `422 {"context": {"offer": "required"}}`.

    Redis would lose these, and re-probing costs a deliberate 422 on every first
    send. It also gives staff a real queue: companies not on Didox yet.
    """

    __tablename__ = "didox_companies"

    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    tin: Mapped[str] = mapped_column(Text, nullable=False)
    signup_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offer_signed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Poller cursor. Deliberately overlapped by a day when used: Didox's
    #: `dateFromUpdated` has DAY granularity, so this is not an exactly-once
    #: cursor and every consumer downstream of it must be idempotent.
    last_polled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_ready(self) -> bool:
        """Both onboarding steps done — documents may be sent."""
        return self.signup_at is not None and self.offer_signed_at is not None
