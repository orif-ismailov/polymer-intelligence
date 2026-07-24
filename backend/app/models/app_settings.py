"""
Runtime application settings (Phase 8d).

A small key→JSONB store for operator-editable knobs that must change WITHOUT a redeploy:
whether AI summaries run, which model/prompt the news extractor uses, whether news needs
per-article approval, and whether reports auto-publish. Env config (app/core/config.py)
remains the source of truth for secrets and infra; this table is only for the handful of
runtime toggles the admin panel exposes. Unknown/unset keys fall back to code defaults
(see app/services/settings_service.py) — the table stores only overrides.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class AppSetting(Base):
    """One operator-editable setting override (key → JSONB value)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
