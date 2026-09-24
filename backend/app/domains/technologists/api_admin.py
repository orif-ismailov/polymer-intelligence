"""Staff moderation of technologist profiles. Under /api/v1/admin.

Reading the queue takes the `technologists` page at `read`; approving, rejecting
and suspending take it at `write`. Staff see the LIVE row (what the expert
submitted) next to the snapshot the catalog currently serves, because approving
an edit is a comparison between the two.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.technologists import profiles
from app.domains.technologists.models import TechnologistProfile
from app.domains.technologists.schemas import AdminTechnologistOut, ModerationReasonIn
from app.models.staff import StaffUser
from app.services import storage_service

router = APIRouter(
    prefix="/admin/technologists",
    tags=["admin-technologists"],
    dependencies=[Depends(require_page("technologists", "read"))],
)


def _out(db: Session, profile: TechnologistProfile) -> AdminTechnologistOut:
    account = db.get(UserAccount, profile.user_account_id)
    return AdminTechnologistOut(
        id=profile.id,
        user_account_id=profile.user_account_id,
        account_name=account.name if account else None,
        account_phone=account.phone if account else None,
        full_name=profile.full_name,
        title=profile.title,
        country=profile.country,
        city=profile.city,
        photo_url=f"/api/v1/admin/technologists/{profile.id}/photo" if profile.photo_key else None,
        years_experience=profile.years_experience,
        projects_count=profile.projects_count,
        countries_count=profile.countries_count,
        bio=profile.bio,
        industries=list(profile.industries or []),
        processes=list(profile.processes or []),
        materials=list(profile.materials or []),
        equipment_brands=list(profile.equipment_brands or []),
        work_formats=list(profile.work_formats or []),
        languages=list(profile.languages or []),
        contact_phone=profile.contact_phone,
        contact_email=profile.contact_email,
        status=profile.status,
        rejection_reason=profile.rejection_reason,
        submitted_at=profile.submitted_at,
        reviewed_at=profile.reviewed_at,
        reviewed_by=profile.reviewed_by,
        is_listed=profiles.is_listed(profile),
        missing_fields=profiles.missing_fields(profile),
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        published_snapshot=profile.published_snapshot,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _profile_or_404(db: Session, profile_id: int) -> TechnologistProfile:
    profile = db.get(TechnologistProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return profile


def _conflict() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invalid_transition")


@router.get("", response_model=list[AdminTechnologistOut], summary="The moderation queue")
def list_technologists(
    profile_status: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AdminTechnologistOut]:
    rows = profiles.list_for_staff(db, status=profile_status, limit=limit, offset=offset)
    return [_out(db, p) for p in rows]


@router.get("/{profile_id}", response_model=AdminTechnologistOut)
def get_technologist(profile_id: int, db: Session = Depends(get_db)) -> AdminTechnologistOut:
    return _out(db, _profile_or_404(db, profile_id))


@router.get("/{profile_id}/photo", summary="The LIVE portrait (staff review)")
def get_photo(profile_id: int, db: Session = Depends(get_db)) -> Response:
    profile = _profile_or_404(db, profile_id)
    if not profile.photo_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    body = storage_service.get_object_bytes(profile.photo_key)
    media_type = "image/png" if profile.photo_key.endswith(".png") else "image/jpeg"
    return Response(content=body, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/{profile_id}/approve", response_model=AdminTechnologistOut)
def approve(
    profile_id: int,
    actor: StaffUser = Depends(require_page("technologists", "write")),
    db: Session = Depends(get_db),
) -> AdminTechnologistOut:
    profile = _profile_or_404(db, profile_id)
    try:
        profiles.approve(db, profile, actor.id)
    except profiles.InvalidProfileTransition as exc:
        raise _conflict() from exc
    db.commit()
    return _out(db, profile)


@router.post("/{profile_id}/reject", response_model=AdminTechnologistOut)
def reject(
    profile_id: int,
    body: ModerationReasonIn,
    actor: StaffUser = Depends(require_page("technologists", "write")),
    db: Session = Depends(get_db),
) -> AdminTechnologistOut:
    profile = _profile_or_404(db, profile_id)
    try:
        profiles.reject(db, profile, actor.id, body.reason)
    except profiles.InvalidProfileTransition as exc:
        raise _conflict() from exc
    db.commit()
    return _out(db, profile)


@router.post("/{profile_id}/suspend", response_model=AdminTechnologistOut)
def suspend(
    profile_id: int,
    body: ModerationReasonIn,
    actor: StaffUser = Depends(require_page("technologists", "write")),
    db: Session = Depends(get_db),
) -> AdminTechnologistOut:
    profile = _profile_or_404(db, profile_id)
    try:
        profiles.suspend(db, profile, actor.id, body.reason)
    except profiles.InvalidProfileTransition as exc:
        raise _conflict() from exc
    db.commit()
    return _out(db, profile)
