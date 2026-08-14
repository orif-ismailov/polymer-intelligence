"""Payments bounded context (R4 / P3 — escrow).

Money moves through a partner bank, never through this platform. What lives here
is the *record* of that movement: one `EscrowPayment` per deal, and a raw inbox
of provider callbacks.

Two things are deliberately absent:

  * **No bank account details.** Not an account number, not an IBAN, not an MFO.
    The invoice the buyer pays is issued by the bank; storing the account would
    make this table a payment-fraud target for no operational gain.
  * **No status logic.** `escrow_service` owns the transitions, the row lock and
    the deal side effects. This module is only the schema.

`mode` is frozen at creation on purpose. An operator may flip the `escrow_mode`
runtime setting at any time, but a payment opened on the stub rail stays a stub
payment — otherwise a flip would retroactively change how existing rows are
allowed to be marked.

Boundary rule (`.planning/deal-lifecycle/00-CONTEXT.md`): this context reaches
the deals context by id and through `deal_service.transition()`, never by
writing to a deals table.
"""

from __future__ import annotations

import datetime
import decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import EscrowStatus

#: The rails a payment can be opened on. `stub` = an operator confirms movement
#: by hand against the bank statement; `live` = a bank adapter does (P7).
ESCROW_MODE_STUB = "stub"
ESCROW_MODE_LIVE = "live"


class EscrowPayment(Base):
    """The escrow record for one deal. At most one row per deal, ever."""

    __tablename__ = "escrow_payments"
    __table_args__ = (
        # One payment per deal: every lookup in the money path goes BY deal, and
        # two rows would make "is this deal paid?" ambiguous.
        UniqueConstraint("deal_id", name="uq_escrow_payments_deal"),
        Index("ix_escrow_payments_status", "status", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    deal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="UZS", server_default="UZS"
    )
    status: Mapped[EscrowStatus] = mapped_column(
        PgEnum(EscrowStatus, name="escrow_status", create_type=False),
        nullable=False,
        default=EscrowStatus.pending,
        server_default="pending",
    )
    #: 'stub' | 'live' — the rail this payment was opened on, frozen at creation.
    mode: Mapped[str] = mapped_column(
        Text, nullable=False, default=ESCROW_MODE_STUB, server_default=ESCROW_MODE_STUB
    )
    #: The bank's own operation id (live only). Never a account/card number.
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    funded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Who asserted the movement in stub mode (staff_users.id). NULL on the live
    # rail, where the provider event is the evidence instead.
    funded_marked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    released_marked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refunded_marked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: The operator's mandatory comment on the last mark (bank reference etc.).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProviderEvent(Base):
    """Raw inbox for external provider callbacks (webhooks).

    Created here rather than in P7 because the idempotency guarantee belongs to
    the schema: `(provider, external_id)` is unique, so a bank retrying a
    callback collides on insert instead of being applied twice. The row is kept
    verbatim — parsing happens later, and a payload we failed to understand is
    still evidence.
    """

    __tablename__ = "provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_provider_events_external"),
        Index("ix_provider_events_unprocessed", "processed", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
