"""
Admin users router — GET /admin/users staff list (admin-only).

Phase 4, Plan 04: Returns the staff user list for the Assign Owner dropdown
on the Purchase Requests detail panel.

Security (T-04-13):
  - require_admin: only admin role may access this endpoint.
  - SELECT excludes password_hash: the query only selects
    id, email, role, is_active, created_at — never password_hash.
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.models.staff import StaffUser
from app.schemas.dashboard import StaffUserItem

router = APIRouter(prefix="/admin", tags=["admin-users"])


@router.get(
    "/users",
    response_model=list[StaffUserItem],
    summary="List staff users (admin-only)",
    description=(
        "Returns the staff user list (id, email, role, is_active, created_at). "
        "Admin-only (T-04-13: never exposes password_hash). "
        "Used by the Assign Owner dropdown on the Purchase Requests detail panel."
    ),
)
def get_staff_users(
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[StaffUserItem]:
    """GET /admin/users — return all staff users.

    T-04-13: Only non-sensitive fields are selected — password_hash is
    explicitly excluded from the query.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Valid token but user is not admin.
    """
    rows = db.execute(
        sa.text(
            """
            SELECT id, email, role::text, is_active, created_at
            FROM staff_users
            ORDER BY id
            """
        )
    ).fetchall()

    return [
        StaffUserItem(
            id=row[0],
            email=row[1],
            role=row[2],
            is_active=row[3],
            created_at=row[4],
        )
        for row in rows
    ]
