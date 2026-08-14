"""Portal notification-centre endpoints (R2 W3 T3.5). Under /api/v1/portal.

Account-scoped (not company-scoped): a person's notifications across all their
companies. Polling model — the portal refetches on an interval + on window focus
(SSE is deferred to R4+). All rows carry i18n keys + params, rendered client-side.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.notifications.schemas import (
    MarkReadIn,
    PortalNotificationOut,
    PortalNotificationPage,
)
from app.services import notification_service

router = APIRouter(prefix="/portal/notifications", tags=["portal-notifications"])


@router.get("", response_model=PortalNotificationPage, summary="List notifications (paged)")
def list_notifications(
    unread_only: bool = Query(default=False),
    cursor: int | None = Query(default=None, description="Keyset: last id of the previous page"),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> PortalNotificationPage:
    rows = notification_service.list_notifications(
        db, account.id, unread_only=unread_only, cursor=cursor, limit=limit
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return PortalNotificationPage(
        items=[PortalNotificationOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/unread-count", summary="Unread notification count")
def unread_count(
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, int]:
    return {"count": notification_service.unread_count(db, account.id)}


@router.post("/read", summary="Mark notifications read (ids | all)")
def mark_read(
    body: MarkReadIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, int]:
    marked = notification_service.mark_read(
        db, account.id, ids=body.ids, mark_all=body.all
    )
    db.commit()
    return {"marked": marked}
