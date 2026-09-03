"""
Runtime setting OVERRIDES — the layer on top of the env contract (migration 0045).

`.env` remains the complete contract and the default for every switch: what
`deploy/.env.example` documents is what a deployment runs unless somebody says
otherwise from the admin panel. This table is where "otherwise" is recorded, one
row per overridden key, and nothing else.

That distinction is the whole design. A table that stored a VALUE alongside a
default written in Python was the arrangement migration `0043` removed, because a
fresh database had no rows and every rail then ran on something invisible. Here a
missing row means the env value — a line an operator can read — and a present row
is displayed as an override, with the env value beside it and a reset action.

See `app/services/settings_service.py` for the resolution order and the write
path, and `app/api/admin_settings.py` for the surface.

Kernel, not a domain: this is configuration substrate with no bounded context of
its own, like `staff.py`.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class AppSetting(Base):
    """One operator override: a `settings_service.SPECS` key → its JSONB value."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    #: JSONB so a bool stays a bool through the round trip, and so `null` is a
    #: legal override for the nullable settings (the notify chat ids) rather
    #: than being indistinguishable from "no row".
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    #: True → `value` is Fernet ciphertext (`app.core.crypto`), not plaintext.
    #:
    #: Stored on the ROW rather than looked up in SPECS because the loader must
    #: know how to read a row before it can consult anything else — and because
    #: a spec that stops being `sensitive` must not silently start handing
    #: ciphertext to a provider as though it were a token.
    is_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
