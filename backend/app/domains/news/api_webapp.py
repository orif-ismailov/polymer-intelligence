"""
/webapp/news — market news for the Telegram Web App News tab.

Two surfaces:
- `/webapp/news/articles[/{id}]` — individual classified news articles (Phase 7e),
  rendered as cards; sourced from kind='news' signals' ai.news block.
- `/webapp/news[/{report_id}]` — published daily reports (the whole-day digest).

Only `published` reports are returned (human-in-the-loop: staff approve → publish).
Authenticated via initData like the rest of the webapp surface.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.domains.news import reports as report_service
from app.domains.news import service as news_service
from app.domains.news.schemas import (
    NewsArticleCard,
    NewsArticleDetail,
    NewsFilterOptions,
    ReportPublicOut,
    ReportPublicSummary,
)
from app.models.requests import Client

router = APIRouter(prefix="/webapp/news", tags=["webapp-news"])

NewsScope = Literal["all", "uzbekistan", "global", "producers"]
NewsSort = Literal["newest", "importance", "category", "products", "country", "company"]
NewsImportanceFilter = Literal["high", "medium", "low"]


# ── News article cards (Phase 7e) ──────────────────────────────────────────────────
# Declared before the /{report_id} routes so "articles" is not matched as a report id.

@router.get("/articles", response_model=list[NewsArticleCard], summary="List news article cards")
def list_articles(
    limit: int = Query(default=30, ge=1, le=100),
    days: int = Query(default=7, ge=1, le=30),
    q: str | None = Query(default=None, max_length=100, description="Full-text search over headline/summary/etc."),
    scope: NewsScope | None = Query(default=None, description="Top-nav tab: all/uzbekistan/global/producers."),
    category: str | None = Query(default=None, max_length=60),
    country: str | None = Query(default=None, max_length=60),
    company: str | None = Query(default=None, max_length=80),
    product: str | None = Query(default=None, max_length=40),
    importance: NewsImportanceFilter | None = Query(default=None),
    source_id: int | None = Query(default=None, ge=1),
    sort: NewsSort | None = Query(default=None, description="Default: importance→recency."),
    lang: str | None = Query(default=None, max_length=8, description="Localize display fields (ru/uz/en)."),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[NewsArticleCard]:
    articles = news_service.list_news_articles(
        db,
        limit=limit,
        days=days,
        q=q,
        scope=None if scope == "all" else scope,
        category=category,
        country=country,
        company=company,
        product=product,
        importance=importance,
        source_id=source_id,
        sort=sort,
        lang=lang,
    )
    return [NewsArticleCard.model_validate(a) for a in articles]


@router.get("/articles/filters", response_model=NewsFilterOptions, summary="News filter facets")
def article_filters(
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> NewsFilterOptions:
    return NewsFilterOptions.model_validate(news_service.list_news_filter_options(db, days=days))


@router.get("/articles/{signal_id}", response_model=NewsArticleDetail, summary="Get a news article")
def get_article(
    signal_id: int,
    lang: str | None = Query(default=None, max_length=8, description="Localize display fields (ru/uz/en)."),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> NewsArticleDetail:
    article = news_service.get_news_article(db, signal_id, lang=lang)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return NewsArticleDetail.model_validate(article)


# ── Published reports (daily digest) ───────────────────────────────────────────────

@router.get("", response_model=list[ReportPublicSummary], summary="List published reports")
def list_news(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[ReportPublicSummary]:
    return report_service.list_published(db, limit=limit)  # type: ignore[return-value]


@router.get("/{report_id}", response_model=ReportPublicOut, summary="Get a published report")
def get_news(
    report_id: int,
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> ReportPublicOut:
    report = report_service.get_published(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    out = ReportPublicOut.model_validate(report)
    # The localized AI summary/forecast lives in the snapshot, not a column.
    snapshot = report.data_snapshot or {}
    i18n = snapshot.get("i18n")
    out.i18n = i18n if isinstance(i18n, dict) else None
    return out
