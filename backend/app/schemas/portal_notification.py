"""Portal notification schemas (R2 W3 T3.5).

Notifications carry i18n keys + params, never pre-rendered text — the portal renders
in the reader's language at display time.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class PortalNotificationOut(BaseModel):
    """One in-portal notification (i18n keys + params, not rendered text)."""

    id: int
    kind: str
    title_key: str
    body_key: str
    params: dict[str, object]
    entity: str | None
    entity_id: str | None
    read_at: datetime.datetime | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class PortalNotificationPage(BaseModel):
    """A keyset page of notifications; ``next_cursor`` is the id to pass next (or None)."""

    items: list[PortalNotificationOut]
    next_cursor: int | None = None


class MarkReadIn(BaseModel):
    """Body for POST /portal/notifications/read — specific ids OR all unread."""

    ids: list[int] | None = None
    all: bool = False
