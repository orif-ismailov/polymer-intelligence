"""
/admin/settings + /admin/news — runtime settings, news-ops stats, and the news
approval queue for the internal dashboard (Phase 8d/8e).

Settings (GET/PUT) are admin-only; the news-ops surface (stats, run-parser, approval
queue) is analyst-or-admin. Editing a setting takes effect on the next task run — no
redeploy. Approving/rejecting a news article flips its ai.news.approval state.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_analyst_or_admin
from app.core.db import get_db
from app.domains.news import reports as report_service
from app.domains.news import service as news_service
from app.models.staff import StaffUser
from app.schemas.admin_settings import (
    NewsStats,
    PendingNewsItem,
    RunParserResult,
    SettingItem,
    SourceActivity,
)
from app.services import settings_service, source_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-settings"])


# ── Runtime settings ───────────────────────────────────────────────────────────────

@router.get("/settings", response_model=list[SettingItem], summary="List runtime settings")
def list_settings(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_admin),
) -> list[SettingItem]:
    return [SettingItem.model_validate(s) for s in settings_service.get_all(db)]


@router.put("/settings", response_model=list[SettingItem], summary="Update runtime settings")
def update_settings(
    updates: dict[str, Any],
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_admin),
) -> list[SettingItem]:
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No settings provided")
    try:
        result = settings_service.set_many(db, updates, user.id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown setting: {exc.args[0]}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return [SettingItem.model_validate(s) for s in result]


# ── News-ops (dashboard admin panel) ───────────────────────────────────────────────

@router.get("/news/stats", response_model=NewsStats, summary="News-ops dashboard stats")
def news_stats(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> NewsStats:
    ai_enabled = bool(settings_service.get(db, "news_ai_enabled"))
    return NewsStats.model_validate(report_service.news_admin_stats(db, ai_enabled=ai_enabled))


@router.post("/news/run-parser", response_model=RunParserResult, summary="Trigger a news scan/parse now")
def run_parser(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_admin),
) -> RunParserResult:
    """Enqueue the RSS news fetch driver now (the 'Run Parser Now' button).

    Returns which sources the scan will hit so the UI can show it immediately; results
    stream into GET /admin/news/activity as the workers fetch + parse each source.
    """
    sources = source_service.enabled_rss_source_names(db)
    enqueued: list[str] = []
    try:
        from app.tasks.celery_app import celery_app  # noqa: PLC0415

        celery_app.send_task("rss_fetch", queue="ingest")
        enqueued.append("rss_fetch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin.run_parser.enqueue_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not enqueue the parser"
        ) from exc
    return RunParserResult(enqueued=enqueued, sources=sources, count=len(sources))


@router.get("/news/activity", response_model=list[SourceActivity], summary="Per-source scan activity")
def news_activity(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[SourceActivity]:
    return [SourceActivity.model_validate(a) for a in source_service.news_source_activity(db)]


@router.get(
    "/news/pending", response_model=list[PendingNewsItem], summary="News awaiting approval"
)
def pending_news(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[PendingNewsItem]:
    return [PendingNewsItem.model_validate(a) for a in news_service.list_pending_news(db)]


@router.post("/news/{signal_id}/approve", summary="Approve a pending news article")
def approve_news(
    signal_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, object]:
    if not news_service.set_news_approval(db, signal_id, approved=True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found")
    db.commit()
    return {"id": signal_id, "approval": "approved"}


@router.post("/news/{signal_id}/reject", summary="Reject a pending news article")
def reject_news(
    signal_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> dict[str, object]:
    if not news_service.set_news_approval(db, signal_id, approved=False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found")
    db.commit()
    return {"id": signal_id, "approval": "rejected"}
