"""
Dashboard home overview API.

GET /dashboard/summary — KPIs + top buyer requests / seller offers / AI signals
for the dashboard overview page. Staff-auth (read-only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user
from app.core.db import get_db
from app.models.staff import StaffUser
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_summary_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard home overview — KPIs + top panels (staff)",
)
def dashboard_summary(
    db: Session = Depends(get_db),
    _: StaffUser = Depends(get_current_staff_user),
) -> DashboardSummary:
    """Return the overview payload for the dashboard home page."""
    return get_dashboard_summary(db)
