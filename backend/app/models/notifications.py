"""
Portal notification centre (R2 — ARCHITECTURE Amendment A2): portal_notifications.

An in-portal notification addressed to one ``user_accounts`` row. Rows are written
by ``notification_service.notify_account`` inside the producing transaction (via the
``domain_events`` outbox consumers) and read by the portal notification centre.

Design (R2-PLAN W1 T1.1):
  * ``kind`` is plain Text by design — extensible without a migration (values such
    as ``request_status``, ``inquiry_approved``, ``inquiry_reply``,
    ``verification_decided``, ``offer_moderated``, ``news_breaking``).
  * Bodies are NEVER pre-rendered: ``title_key`` / ``body_key`` are i18n message
    keys and ``params`` carries the interpolation values, so the portal renders in
    the reader's language (ru/uz/en) at display time.
  * ``entity`` / ``entity_id`` are an optional deep-link target (e.g. ``request`` +
    the request id) for the notification-centre click-through.
  * ``read_at`` NULL ⇒ unread. The ``(user_account_id, read_at, id DESC)`` index
    backs both the unread-count query and the paged feed.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class PortalNotification(Base):
    """An in-portal notification for a single portal account."""

    __tablename__ = "portal_notifications"
    __table_args__ = (
        # Backs the unread-count query and the paged feed. read_at in the middle
        # keeps ``WHERE read_at IS NULL`` an index-range scan; the trailing ``id``
        # column is scanned backward for the newest-first (``ORDER BY id DESC``)
        # feed — a btree is bidirectional, so plain ASC storage is optimal here.
        Index(
            "ix_portal_notifications_account_unread",
            "user_account_id",
            "read_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)                        # extensible; plain Text by design
    title_key: Mapped[str] = mapped_column(Text, nullable=False)                   # i18n message key
    body_key: Mapped[str] = mapped_column(Text, nullable=False)                    # i18n message key
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )                                                                              # interpolation values (never pre-rendered text)
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)                # deep-link target type
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)             # deep-link target id
    read_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )                                                                              # NULL ⇒ unread
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
