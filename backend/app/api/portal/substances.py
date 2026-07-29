"""Portal substance picker (P5 W2 — T2.4, FR-C2). Under /api/v1/portal.

Read-only search over the active registry for the offer form. Requires a portal
account but no company: a seller picks the substance while drafting, before the
form knows which company is publishing.

The projection carries the regulation level so the seller sees "licence
required" while choosing — not after submitting a finished form and getting a
409 back.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.models.accounts import UserAccount
from app.schemas.substance import SubstanceBrief
from app.services import substance_service

router = APIRouter(prefix="/portal/substances", tags=["portal-compliance"])


@router.get("", response_model=list[SubstanceBrief], summary="Search the substance registry")
def search_substances(
    q: str = Query(default="", max_length=120),
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> list[SubstanceBrief]:
    """Active substances matching name / synonym / CAS / HS code (empty q → [])."""
    return substance_service.search(db, q)  # type: ignore[return-value]
