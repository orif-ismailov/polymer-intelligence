"""
Integration gateway call log (R3 — ARCHITECTURE §5, §12).

Every outbound call to an external verification provider (the E-IMZO sidecar now;
gov registry / bank / e-invoice adapters later) writes one `integration_call_log`
row: which provider/operation, whether it succeeded, latency, and a redacted error.
It is the observability + circuit-breaker audit trail for the gateway, and the
data behind `/admin/analytics`. Never holds evidence, only call metadata. NEVER
store request/response bodies here (they may carry PINFL/PKCS#7); evidence lives
in the immutable `signature_evidence`/`registry_snapshots` tables instead.

Pruned at 90 days (§13) by `prune_integration_call_log` in `app/tasks/retention.py`,
which owns the number. This docstring claimed that retention for a year while
nothing implemented it — fine at a few hundred E-IMZO calls, not fine against a
Didox package of a million requests a month.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class IntegrationCallLog(Base):
    """One outbound provider call (metadata only — no bodies)."""

    __tablename__ = "integration_call_log"
    __table_args__ = (
        Index("ix_integration_call_log_created", "created_at"),  # prune scan (90d)
        Index("ix_integration_call_log_provider", "provider", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)                   # e.g. 'eimzo'
    operation: Mapped[str] = mapped_column(Text, nullable=False)                  # e.g. 'verify_pkcs7'
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)       # HTTP status when applicable
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)               # redacted error class/message
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
