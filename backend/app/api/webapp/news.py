"""
/webapp/news — published market reports for the Telegram Web App News tab.

Only `published` reports are returned (human-in-the-loop: staff approve → publish).
Authenticated via initData like the rest of the webapp surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.requests import Client
from app.schemas.reports import ReportPublicOut, ReportPublicSummary
from app.services import report_service

router = APIRouter(prefix="/webapp/news", tags=["webapp-news"])


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
    return report  # type: ignore[return-value]
