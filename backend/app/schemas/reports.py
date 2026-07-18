"""
Pydantic schemas for the news engine (Phase 3).

Public (webapp) views expose only published reports' display fields; the admin
(dashboard) view adds status, generator provenance, and the data snapshot.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ReportKind, ReportStatus


class ReportPublicSummary(BaseModel):
    """List item for the webapp News feed (published reports)."""

    id: int
    title: str
    period_start: datetime.date
    period_end: datetime.date
    published_at: datetime.datetime | None

    model_config = {"from_attributes": True}


class ReportPublicOut(ReportPublicSummary):
    """Full published report for the News detail view.

    `i18n` carries the AI summary + forecast in ru/en/uz (from data_snapshot) so the
    webapp can show the digest in the client's language; None for pre-digest reports.
    """

    content_md: str
    i18n: dict[str, Any] | None = None


class NewsArticleCard(BaseModel):
    """A single classified news article for the webapp News cards (Phase 7e).

    Sourced from a kind='news' signal's ai.news block (not a report). `image_url` is
    reserved (no image extracted yet); the card degrades to a category icon.
    """

    id: int
    headline: str
    category: str | None = None
    importance: str | None = None
    market_impact: str | None = None
    summary: str | None = None
    country: str | None = None
    companies: list[str] = []
    related_products: list[str] = []
    source_name: str | None = None
    published_at: str | None = None
    image_url: str | None = None


class NewsArticleDetail(NewsArticleCard):
    """Full article for the "read more" view: original body + link to the source."""

    body: str | None = None
    source_url: str | None = None


class ReportAdminOut(BaseModel):
    """Dashboard review representation (any non-rejected status)."""

    id: int
    title: str
    kind: ReportKind
    status: ReportStatus
    content_md: str
    generated_by: str | None
    data_snapshot: dict[str, Any]
    period_start: datetime.date
    period_end: datetime.date
    published_at: datetime.datetime | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
