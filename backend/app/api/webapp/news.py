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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.requests import Client
from app.schemas.reports import (
    NewsArticleCard,
    NewsArticleDetail,
    ReportPublicOut,
    ReportPublicSummary,
)
from app.services import news_service, report_service

router = APIRouter(prefix="/webapp/news", tags=["webapp-news"])


# ── News article cards (Phase 7e) ──────────────────────────────────────────────────
# Declared before the /{report_id} routes so "articles" is not matched as a report id.

@router.get("/articles", response_model=list[NewsArticleCard], summary="List news article cards")
def list_articles(
    limit: int = Query(default=30, ge=1, le=100),
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[NewsArticleCard]:
    articles = news_service.list_news_articles(db, limit=limit, days=days)
    return [NewsArticleCard.model_validate(a) for a in articles]


@router.get("/articles/{signal_id}", response_model=NewsArticleDetail, summary="Get a news article")
def get_article(
    signal_id: int,
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> NewsArticleDetail:
    article = news_service.get_news_article(db, signal_id)
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
