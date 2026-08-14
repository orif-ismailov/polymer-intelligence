"""
/admin/substances — the registry of regulated chemistry (P5 W2 — T2.3, FR-C1).

Analysts may read it; only an admin may change it. That split is deliberate:
this table decides what the platform will and will not let a company sell, so
editing it is closer to changing a policy than to moderating a listing.

There is no DELETE. Offers point at substances and a blocked offer has to stay
explainable after the list that blocked it is superseded — so a row is
deactivated, never removed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_analyst_or_admin
from app.core.db import get_db
from app.domains.compliance import substances as substance_service
from app.domains.compliance.substance_schemas import SubstanceIn, SubstanceOut
from app.models.enums import RegulationLevel
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin/substances", tags=["compliance"])


def _or_404(db: Session, substance_id: int):  # noqa: ANN202
    row = substance_service.get(db, substance_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Substance not found")
    return row


def _conflict() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="substance_exists")


@router.get("", response_model=list[SubstanceOut], summary="List substances")
def list_substances(
    q: str | None = None,
    level: RegulationLevel | None = None,
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[SubstanceOut]:
    """Inactive rows are included by default — staff need to see what was retired."""
    return substance_service.list_all(  # type: ignore[return-value]
        db, q=q, level=level, include_inactive=include_inactive
    )


@router.post(
    "",
    response_model=SubstanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a substance",
)
def create_substance(
    body: SubstanceIn,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_admin),
) -> SubstanceOut:
    try:
        row = substance_service.create(db, body, staff_user_id=user.id)
    except substance_service.SubstanceExists as exc:
        raise _conflict() from exc
    db.commit()
    return row  # type: ignore[return-value]


@router.get("/{substance_id}", response_model=SubstanceOut, summary="One substance")
def get_substance(
    substance_id: int,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> SubstanceOut:
    return _or_404(db, substance_id)


@router.patch("/{substance_id}", response_model=SubstanceOut, summary="Edit a substance")
def update_substance(
    substance_id: int,
    body: SubstanceIn,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_admin),
) -> SubstanceOut:
    """Full replacement. Takes the row out of the seed's hands (seed_revision → NULL)."""
    row = _or_404(db, substance_id)
    try:
        substance_service.update(db, row, body, staff_user_id=user.id)
    except substance_service.SubstanceExists as exc:
        raise _conflict() from exc
    db.commit()
    return row  # type: ignore[return-value]


@router.post(
    "/{substance_id}/deactivate", response_model=SubstanceOut, summary="Retire a substance"
)
def deactivate_substance(
    substance_id: int,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_admin),
) -> SubstanceOut:
    row = _or_404(db, substance_id)
    substance_service.set_active(db, row, active=False, staff_user_id=user.id)
    db.commit()
    return row  # type: ignore[return-value]


@router.post(
    "/{substance_id}/activate", response_model=SubstanceOut, summary="Restore a substance"
)
def activate_substance(
    substance_id: int,
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_admin),
) -> SubstanceOut:
    row = _or_404(db, substance_id)
    substance_service.set_active(db, row, active=True, staff_user_id=user.id)
    db.commit()
    return row  # type: ignore[return-value]
