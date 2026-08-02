"""Logistics service requests — a buyer's cargo + route ask to one carrier.

The lighter sibling of `factory_rfqs`. A factory RFQ is priced against a
published offer and carries compliance documents and commercial terms; a
logistics request has no offer to point at — what a carrier quotes is a *lane*,
so the payload is the cargo and the two ends of the route
(`docs/new-design/logistics_request.png`, «Быстрая заявка на логистику»).

Deliberately one table, no documents and no thread: the sheet is one screen with
seven fields, and every extra slot on it is a reason not to send.
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
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import LogisticsRequestStatus


class LogisticsRequest(Base):
    """A buyer company's transport request to one verified logistics provider."""

    __tablename__ = "logistics_requests"
    __table_args__ = (
        CheckConstraint(
            "buyer_company_id <> logistics_company_id",
            name="ck_logistics_request_parties_distinct",
        ),
        CheckConstraint("volume > 0", name="ck_logistics_request_volume_positive"),
        Index("ix_logistics_requests_buyer_status", "buyer_company_id", "status"),
        Index(
            "ix_logistics_requests_carrier_status",
            "logistics_company_id",
            "status",
        ),
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
    logistics_company_id: Mapped[int] = mapped_column(
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
