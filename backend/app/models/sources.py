"""
Sources and raw data layer: sources, raw_items, parse_runs.

DDL source: docs/polymer-intelligence-db-architecture.md §2.

INVARIANT: is_enabled = true => last_test_ok_at IS NOT NULL
(enforced via service-layer validation, not DB CHECK, per constraints.md).
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import ParseStatus, SourceKind


class Source(Base):
    """Data source registry: UZEX, Telegram channels, external indices, etc."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(
        PgEnum(SourceKind, name="source_kind", create_type=False),
        nullable=False,
    )
    adapter: Mapped[str] = mapped_column(Text, nullable=False)  # adapter registry name
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)             # 'UZ', 'CN', 'RU'
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_test_ok_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )                                                                             # enables: invariant guard
    last_fetch_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    raw_items: Mapped[list[RawItem]] = relationship(
        "RawItem", back_populates="source"
    )


class RawItem(Base):
    """Immutable raw data store — never UPDATE on content.

    All incoming data is saved here before parsing.
    """

    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_raw_items_source_content"),
        Index(
            "ix_raw_items_parse_status_pending",
            "parse_status",
            "fetched_at",
            postgresql_where="parse_status = 'pending'",
        ),
        Index("ix_raw_items_source_fetched", "source_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )                                                                             # TG msg_id, UZEX lot#
    content: Mapped[str | None] = mapped_column(Text, nullable=True)             # text / HTML fragment
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # structured data
    content_hash: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )                                                                             # sha256 for dedup
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )                                                                             # source event time
    parse_status: Mapped[ParseStatus] = mapped_column(
        PgEnum(ParseStatus, name="parse_status", create_type=False),
        nullable=False,
        default=ParseStatus.pending,
        server_default="pending",
    )
    parse_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )

    # Relationships
    source: Mapped[Source] = relationship("Source", back_populates="raw_items")
    parse_runs: Mapped[list[ParseRun]] = relationship(
        "ParseRun", back_populates="raw_item"
    )


class ParseRun(Base):
    """LLM parse journal: what model, what prompt, what result.

    Enables re-parsing with new prompts without losing original data.

    parser discriminators:
    - 'uzex_table_v1' / 'uzex_table_v2': rule-based UZEX adapters (no LLM call)
    - 'llm_extract': Phase-5 LLM journal discriminator (Anthropic API via instructor)
    """

    __tablename__ = "parse_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("raw_items.id"), nullable=False
    )
    parser: Mapped[str] = mapped_column(Text, nullable=False)                    # 'uzex_table_v2', 'llm_extract'
    model: Mapped[str | None] = mapped_column(Text, nullable=True)               # 'claude-haiku-4-5', NULL for rule-based
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)                    # 'ok' | 'error' | 'irrelevant'
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase-5 AI journaling: wall-clock LLM call latency in milliseconds.
    # NULL for rule-based runs (parser != 'llm_extract') that involve no network call.
    # Added by migration 0003_phase5_ai_extraction.
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    raw_item: Mapped[RawItem] = relationship("RawItem", back_populates="parse_runs")
