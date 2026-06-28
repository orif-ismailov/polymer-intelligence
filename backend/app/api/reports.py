"""
/admin/reports — news-engine review/approve/publish (internal dashboard).

Analyst or admin only. Human-in-the-loop: a generated report is `draft` →
approve → publish (publish sets published_at and makes it public on the News tab;
channel delivery is a separate task). Generate-now is provided for convenience.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.models.reports import Report
from app.models.staff import StaffUser
from app.schemas.reports import ReportAdminOut
from app.services import report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reports", tags=["reports"])


@router.get("", response_model=list[ReportAdminOut], summary="List reports for review")
def list_reports(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[ReportAdminOut]:
    return report_service.list_for_review(db)  # type: ignore[return-value]


@router.post("/generate", response_model=ReportAdminOut, status_code=status.HTTP_201_CREATED, summary="Generate today's report now")
def generate_now(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> ReportAdminOut:
    report = report_service.generate_report(db)
    db.commit()
    return report  # type: ignore[return-value]


def _get(db: Session, report_id: int) -> Report:
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.post("/{report_id}/approve", response_model=ReportAdminOut, summary="Approve a report")
def approve(
    report_id: int,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_analyst_or_admin),
) -> ReportAdminOut:
    report = report_service.approve_report(db, _get(db, report_id), user.id)
    db.commit()
    return report  # type: ignore[return-value]


@router.post("/{report_id}/publish", response_model=ReportAdminOut, summary="Publish a report")
def publish(
    report_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> ReportAdminOut:
    report = report_service.publish_report(db, _get(db, report_id))
    db.commit()
    # Post to the news channel — best-effort; an outage must not fail the publish.
    try:
        from app.tasks.reports import publish_report_to_channel  # noqa: PLC0415

        publish_report_to_channel.apply_async(args=[report.id], queue="notify", retry=False)
    except Exception:  # noqa: BLE001
        logger.warning("reports.publish.enqueue_failed", extra={"report_id": report.id})
    return report  # type: ignore[return-value]


@router.post("/{report_id}/reject", response_model=ReportAdminOut, summary="Reject a report")
def reject(
    report_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> ReportAdminOut:
    report = report_service.reject_report(db, _get(db, report_id))
    db.commit()
    return report  # type: ignore[return-value]
