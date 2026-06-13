"""
Counterparty entity resolution: counterparties, counterparty_aliases.

DDL source: docs/polymer-intelligence-db-architecture.md §3.

Counterparty linking is non-blocking: counterparty_id is nullable and
resolved by a background process.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import CounterpartyRole, SourceKind


class Counterparty(Base):
    """Canonical counterparty entity (company, trader, etc.)."""

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[CounterpartyRole] = mapped_column(
        PgEnum(CounterpartyRole, name="counterparty_role", create_type=False),
        nullable=False,
        default=CounterpartyRole.unknown,
        server_default="unknown",
    )
    country: Mapped[str | None] = mapped_column(Text, nullable=True)             # char(2) country code
    tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)              # INN if known from UZEX
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    aliases: Mapped[list[CounterpartyAlias]] = relationship(
        "CounterpartyAlias", back_populates="counterparty", cascade="all, delete-orphan"
    )


class CounterpartyAlias(Base):
    """Alternative names/spellings mapping to a canonical counterparty.

    E.g., 'ООО Полимер Трейд', '@polytrade_uz', 'POLIMER TREYD MCHJ' → same company.
    """

    __tablename__ = "counterparty_aliases"
    __table_args__ = (
        UniqueConstraint(
            "alias_norm", "counterparty_id", name="uq_counterparty_aliases_norm"
        ),
        Index("ix_counterparty_aliases_alias_norm", "alias_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counterparty_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("counterparties.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm: Mapped[str] = mapped_column(Text, nullable=False)                # normalized for lookup
    source_kind: Mapped[SourceKind | None] = mapped_column(
        PgEnum(SourceKind, name="source_kind", create_type=False),
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float(precision=None), nullable=False, default=1.0, server_default="1.0"
    )                                                                             # 1.0 = manually confirmed

    # Relationships
    counterparty: Mapped[Counterparty] = relationship(
        "Counterparty", back_populates="aliases"
    )
