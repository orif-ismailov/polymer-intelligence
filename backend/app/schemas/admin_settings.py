"""Schemas for the admin settings + news-ops panel (Phase 8d)."""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class SettingItem(BaseModel):
    """One runtime setting with its resolved value, default, and override flag.

    `value`/`default` cover bool, str, and int settings (e.g. the refresh interval).
    Order matters: bool before int so True/False don't validate as 1/0.
    """

    key: str
    type: str
    label: str
    value: bool | int | str
    default: bool | int | str
    is_overridden: bool


class NewsStats(BaseModel):
    """Admin dashboard news-ops snapshot."""

    total_sources: int
    active_sources: int
    failed_sources: int
    last_scan: datetime.datetime | None
    last_published_report: datetime.datetime | None
    pending_ai_analysis: int
    today_published_news: int
    ai_enabled: bool
    ai_status: str


class PendingNewsItem(BaseModel):
    """A classified news article awaiting approval (dashboard review queue)."""

    id: int
    headline: str
    category: str | None = None
    importance: str | None = None
    summary: str | None = None
    country: str | None = None
    source_name: str | None = None
    published_at: str | None = None


class SourceGroup(BaseModel):
    """A named source group with its member counts (Phase 8f-2)."""

    group: str | None = None  # None = ungrouped
    total: int
    active: int


class SourceBrief(BaseModel):
    """Identity + group for a source (group-assignment UI)."""

    id: int
    name: str
    adapter: str
    country: str | None = None
    group_name: str | None = None
    is_enabled: bool


class SourceGroupUpdate(BaseModel):
    """Assign or clear a source's group."""

    group: str | None = None
