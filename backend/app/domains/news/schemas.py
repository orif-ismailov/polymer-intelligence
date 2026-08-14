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


class NewsSourceRef(BaseModel):
    """One reporting source for a (possibly cross-source-merged) news article."""

    id: int
    name: str | None = None
    published_at: str | None = None


class NewsArticleCard(BaseModel):
    """A single classified news article for the webapp News cards (Phase 7e).

    Sourced from a kind='news' signal's ai.news block (not a report). `image_url` is
    reserved (no image extracted yet); the card degrades to a category icon.

    When the same story is reported by several sources (Phase 7f), they are merged into
    one representative card: `sources` lists every reporting source (original first) and
    `merged_count` is the source count (1 = single-source).
    """

    id: int
    headline: str
    category: str | None = None
    importance: str | None = None
    market_impact: str | None = None
    summary: str | None = None
    analysis: str | None = None
    recommendation: str | None = None
    language: str | None = None
    country: str | None = None
    countries: list[str] = []
    companies: list[str] = []
    related_products: list[str] = []
    source_name: str | None = None
    published_at: str | None = None
    image_url: str | None = None
    sources: list[NewsSourceRef] = []
    merged_count: int = 1


class NewsArticleDetail(NewsArticleCard):
    """Full article for the "read more" view: original body + link to the source."""

    body: str | None = None
    source_url: str | None = None


class NewsFacet(BaseModel):
    """One filterable value (category/country/company/product) + how often it occurs."""

    value: str
    count: int


class NewsFilterOptions(BaseModel):
    """Live facets for the News filter UI — only values present in recent news."""

    categories: list[NewsFacet] = []
    countries: list[NewsFacet] = []
    companies: list[NewsFacet] = []
    products: list[NewsFacet] = []


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
