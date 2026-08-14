"""Portal news endpoints (R2 W3 T3.4). Under /api/v1/portal.

A byte-parity twin of ``/webapp/news`` for portal accounts: the SAME
``news_service`` / ``report_service`` calls and the SAME serializers, only the auth
dependency differs (portal account vs Telegram initData). Because the service and
schema layers are shared, the surface cannot drift from the Mini App (pinned by a
response-model parity test).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
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
from app.models.accounts import UserAccount

router = APIRouter(prefix="/portal/news", tags=["portal-news"])

NewsScope = Literal["all", "uzbekistan", "global", "producers"]
NewsSort = Literal["newest", "importance", "category", "products", "country", "company"]
NewsImportanceFilter = Literal["high", "medium", "low"]


@router.get("/articles", response_model=list[NewsArticleCard], summary="List news article cards")
def list_articles(
    limit: int = Query(default=30, ge=1, le=100),
    days: int = Query(default=7, ge=1, le=30),
    q: str | None = Query(default=None, max_length=100),
    scope: NewsScope | None = Query(default=None),
    category: str | None = Query(default=None, max_length=60),
    country: str | None = Query(default=None, max_length=60),
    company: str | None = Query(default=None, max_length=80),
    product: str | None = Query(default=None, max_length=40),
    importance: NewsImportanceFilter | None = Query(default=None),
    source_id: int | None = Query(default=None, ge=1),
    sort: NewsSort | None = Query(default=None),
    lang: str | None = Query(default=None, max_length=8),
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
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
    _account: UserAccount = Depends(get_current_account),
) -> NewsFilterOptions:
    return NewsFilterOptions.model_validate(news_service.list_news_filter_options(db, days=days))


@router.get("/articles/{signal_id}", response_model=NewsArticleDetail, summary="Get a news article")
def get_article(
    signal_id: int,
    lang: str | None = Query(default=None, max_length=8),
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> NewsArticleDetail:
    article = news_service.get_news_article(db, signal_id, lang=lang)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return NewsArticleDetail.model_validate(article)


@router.get("", response_model=list[ReportPublicSummary], summary="List published reports")
def list_reports(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> list[ReportPublicSummary]:
    return report_service.list_published(db, limit=limit)  # type: ignore[return-value]


@router.get("/{report_id}", response_model=ReportPublicOut, summary="Get a published report")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> ReportPublicOut:
    report = report_service.get_published(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    out = ReportPublicOut.model_validate(report)
    snapshot = report.data_snapshot or {}
    i18n = snapshot.get("i18n")
    out.i18n = i18n if isinstance(i18n, dict) else None
    return out
