"""Logistics service requests — a buyer's cargo + route, broadcast to carriers.

The lighter sibling of `factory_rfqs`. A factory RFQ is priced against a
published offer and carries compliance documents and commercial terms; a
logistics request has no offer to point at — what a carrier quotes is a *lane*,
so the payload is the cargo and the two ends of the route
(`docs/new-design/logistics_request.png`, «Быстрая заявка на логистику»).

**Broadcast, not addressed.** 0035 shipped this with a `logistics_company_id`
pointing at one carrier, which asked the buyer a question they cannot answer: a
shipper with cargo to move does not know which of ten carriers runs that lane.
0038 dropped the column — the request is stated once and every verified carrier
sees it.

Each interested carrier then opens its OWN conversation
(`logistics_request_threads`, unique per `(request, carrier)`), so a buyer
negotiates separately and no carrier reads a competitor's terms.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import LogisticsRequestStatus


class LogisticsRequest(Base):
    """A buyer company's open transport request, readable by every carrier."""

    __tablename__ = "logistics_requests"
    __table_args__ = (
        CheckConstraint("volume > 0", name="ck_logistics_request_volume_positive"),
        Index("ix_logistics_requests_buyer_status", "buyer_company_id", "status"),
        # The pool query: open requests, newest first, for every carrier.
        Index("ix_logistics_requests_open", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    #: `LRQ-YYYY-NNNNNN` — what both parties quote at each other on the phone.
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    buyer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )

    # ── Информация о грузе ───────────────────────────────────────────────────
    cargo_name: Mapped[str] = mapped_column(Text, nullable=False)
    volume: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    volume_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    #: Free text with a preset list on the client, not a PG enum — the same call
    #: `FactoryRfq.incoterms`/`qty_unit` make. Adding «Big-bag» should not be a
    #: migration, and nothing here is filtered or aggregated on.
    packaging_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Маршрут ──────────────────────────────────────────────────────────────
    from_country: Mapped[str] = mapped_column(Text, nullable=False)
    from_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_country: Mapped[str] = mapped_column(Text, nullable=False)
    to_city: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Snapshot of the submitter's phone at submit time.
    #:
    #: NOT collected by the form — the mockup has no contact fields, and it is
    #: right that it does not: the buyer is a member of a verified company, so
    #: who they are is already known. It is denormalised rather than joined
    #: because an account may change its phone, and the carrier needs the number
    #: that was current when the request was sent. There is no name or email
    #: column for the honest reason that `user_accounts` has a NULLABLE name and
    #: no email at all; both derive from the FKs instead.
    contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[LogisticsRequestStatus] = mapped_column(
        PgEnum(
            LogisticsRequestStatus, name="logistics_request_status", create_type=False
        ),
        nullable=False,
        default=LogisticsRequestStatus.submitted,
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


class LogisticsRequestThread(Base):
    """One carrier's conversation with the buyer about one request.

    Keyed on `(request, carrier)` rather than on the company pair the way
    `manufacturer_threads` is: the subject here is the request, and the same two
    companies may be talking about several jobs at once.
    """

    __tablename__ = "logistics_request_threads"
    __table_args__ = (
        UniqueConstraint(
            "logistics_request_id",
            "carrier_company_id",
            name="uq_logistics_thread_request_carrier",
        ),
        Index("ix_logistics_threads_request", "logistics_request_id"),
        Index("ix_logistics_threads_carrier", "carrier_company_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    logistics_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("logistics_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    carrier_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    #: The carrier-side account that opened it. The BUYER side is not stored —
    #: it is `logistics_requests.buyer_company_id`, one join away, and copying it
    #: would be a second place for the same fact to be wrong.
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

    request: Mapped[LogisticsRequest] = relationship("LogisticsRequest")
    messages: Mapped[list[LogisticsRequestMessage]] = relationship(
        "LogisticsRequestMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="LogisticsRequestMessage.id",
    )

    def party_role(self, company_id: int) -> str | None:
        """`"carrier"`, `"buyer"`, or None for anyone else.

        The buyer side needs the loaded request, so a caller that has only the
        thread must pass the request's `buyer_company_id` itself — hence
        `logistics_service.thread_party_role`, which takes both.
        """
        if company_id == self.carrier_company_id:
            return "carrier"
        return None


class LogisticsRequestMessage(Base):
    """One append-only message in a logistics thread."""

    __tablename__ = "logistics_request_messages"
    __table_args__ = (
        Index("ix_logistics_messages_thread", "thread_id", "id"),
        CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL",
            name="ck_logistics_message_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("logistics_request_threads.id", ondelete="CASCADE"),
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

    thread: Mapped[LogisticsRequestThread] = relationship(
        "LogisticsRequestThread", back_populates="messages"
    )
