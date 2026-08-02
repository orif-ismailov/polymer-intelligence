"""Laboratory analysis requests — what needs testing, broadcast to every lab.

The `labaratory_request.png` flow, steps 1–2: a buyer states the material and the
methods once, every verified laboratory sees it, and each interested lab opens
its OWN conversation.

**Not `lab_orders`.** That table (P6, migration 0028) is a different thing and
stays untouched: staff-driven, hung off an offer or a deal, worked by partner
laboratories we phone, and the only path that can set `seller_offers.lab_verified`.
This one is a direct client↔laboratory-company channel — the mockup is explicit
that payment happens off-platform («оплата напрямую лаборатории, IMEX AI не
принимает и не хранит платежи»), so there is no money column here either.

Only a company with a CONFIRMED `laboratory` role can answer, because only a
company has an account; a `lab_partner` has none. That is the same argument
`0038_logistics_broadcast` makes for carriers.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import LabRequestStatus


class LabRequest(Base):
    """A buyer company's open analysis request, readable by every laboratory."""

    __tablename__ = "lab_requests"
    __table_args__ = (
        # The pool query: open requests, newest first, for every laboratory.
        Index("ix_lab_requests_open", "status", "created_at"),
        Index("ix_lab_requests_buyer_status", "buyer_company_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    #: `LBR-YYYY-NNNNNN`. NOT `LAB-` — that prefix is `lab_orders`, and the two
    #: flows coexist; one number format for two different things is a support trap.
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    buyer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )

    # ── Что исследуем? ───────────────────────────────────────────────────────
    #: Catalogue product when the buyer picked one; NULL when they typed a name.
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=True
    )
    product_text: Mapped[str] = mapped_column(Text, nullable=False)
    grade_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: «Тип исследований» — free text with a preset on the client, the call
    #: `FactoryRfq.incoterms` and `logistics_requests.packaging_type` both make.
    #: Nothing filters on it, and adding an option should not be a migration.
    study_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: «Необходимые исследования» — keys from the shared `LAB_METHODS` preset.
    methods: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    #: «Количество образца» — «1 кг» is a quantity AND a unit in one field on
    #: the sheet, so it is one column rather than an invented split.
    sample_qty: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Данные для заявки ────────────────────────────────────────────────────
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_urgent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    desired_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    #: COLLECTED, not snapshotted — unlike the carrier form, this sheet asks for
    #: all three explicitly, and there is nothing to snapshot them from anyway:
    #: `user_accounts.name` is nullable and there is no email column at all.
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[LabRequestStatus] = mapped_column(
        PgEnum(LabRequestStatus, name="lab_request_status", create_type=False),
        nullable=False,
        default=LabRequestStatus.submitted,
        server_default="submitted",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LabRequestThread(Base):
    """One laboratory's conversation with the buyer about one request.

    Keyed on `(request, laboratory)` rather than on the company pair: the subject
    is the request, and the same two companies may be discussing several jobs.
    """

    __tablename__ = "lab_request_threads"
    __table_args__ = (
        UniqueConstraint(
            "lab_request_id",
            "laboratory_company_id",
            name="uq_lab_thread_request_laboratory",
        ),
        Index("ix_lab_threads_request", "lab_request_id"),
        Index("ix_lab_threads_laboratory", "laboratory_company_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lab_request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lab_requests.id", ondelete="CASCADE"), nullable=False
    )
    laboratory_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    #: The laboratory-side account that opened it. The BUYER side is not stored —
    #: it is `lab_requests.buyer_company_id`, one join away, and copying it would
    #: be a second place for the same fact to be wrong.
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    request: Mapped[LabRequest] = relationship("LabRequest")
    messages: Mapped[list[LabRequestMessage]] = relationship(
        "LabRequestMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="LabRequestMessage.id",
    )


class LabRequestMessage(Base):
    """One append-only message in a laboratory thread."""

    __tablename__ = "lab_request_messages"
    __table_args__ = (
        Index("ix_lab_messages_thread", "thread_id", "id"),
        CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL",
            name="ck_lab_message_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lab_request_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    #: Stored, not derived: which SIDE wrote a line must survive an account
    #: moving between companies.
    author_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    file_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped[LabRequestThread] = relationship(
        "LabRequestThread", back_populates="messages"
    )
