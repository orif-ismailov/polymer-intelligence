"""
Transactional outbox (R1 — ARCHITECTURE §5, §7): domain_events.

Cross-context effects go through this outbox: a state change and its event row are
written in the SAME DB transaction (`event_service.emit` → flush only, caller
commits). A beat task (`app.tasks.events.dispatch_domain_events`) polls
unpublished rows (`FOR UPDATE SKIP LOCKED`), fans out to idempotent consumers, and
stamps `published_at`. The `ix_outbox_unpublished` partial index keeps that poll
cheap as the table grows.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.db import Base


class DomainEvent(Base):
    """An outbox event row (append-only until published)."""

    __tablename__ = "domain_events"
    __table_args__ = (
        # Cheap poll of unpublished events (the dispatcher's hot path).
        Index("ix_outbox_unpublished", "id", postgresql_where=text("published_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)                 # see app/services/event_types.py
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
