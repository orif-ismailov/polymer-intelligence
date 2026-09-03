"""
Reports (news engine): reports table.

DDL source: docs/polymer-intelligence-db-architecture.md §8.

Reports have a human-in-the-loop approval workflow:
draft → pending_approval → approved → published (or rejected at any point).
No auto-publish transition exists in code (DEC-human-in-the-loop-reports).
Phase 1: RU-only content.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import ReportKind, ReportStatus


class Report(Base):
    """A market intelligence report (morning/weekly/custom)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[ReportKind] = mapped_column(
        PgEnum(ReportKind, name="report_kind", create_type=False),
        nullable=False,
    )
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)                # markdown → TG/WebApp render
    data_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )                                                                             # numbers at generation time
    status: Mapped[ReportStatus] = mapped_column(
        PgEnum(ReportStatus, name="report_status", create_type=False),
        nullable=False,
        default=ReportStatus.draft,
        server_default="draft",
    )
    generated_by: Mapped[str | None] = mapped_column(Text, nullable=True)        # model + prompt version
    # What the digest call cost. NULL means no LLM call was attempted; 0 would
    # mean one was and spent nothing, which is a different fact. Recorded even
    # when the digest failed and the report fell back to the rule-based summary —
    # this is the platform's most expensive single call (~6.5k output tokens,
    # twice a day) and it was the only LLM caller journalling nothing at all.
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
