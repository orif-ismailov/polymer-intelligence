"""
Staff administration router — /admin/users and /admin/pages (administrator-only).

This is where colleagues are created, given access, and cut off. Until it
existed, `StaffUser(...)` was constructed only by the seeder, so promoting
someone meant running SQL against production and there was no revocation path
at all.

ADMINISTRATOR-ONLY, NOT PAGE-GRANTABLE. Every route here takes `require_admin`
rather than `require_page("adminUsers", …)`, and `adminUsers` is deliberately
absent from `app.core.pages.PAGES`. A grantable write on staff administration is
a privilege-escalation path: whoever can edit staff accounts can mint an
administrator, or widen their own grants, and would then hold every page without
anyone having granted them one. Nothing that hands out authority may itself be
handed out.

Security (T-04-13): `password_hash` is never selected, returned, or logged — a
password change is audited as the fact that it happened, never as a value.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.models.staff import StaffUser
from app.schemas.staff_admin import (
    PageCatalogOut,
    StaffAccessUpdate,
    StaffUserCreate,
    StaffUserDetail,
    StaffUserListItem,
    StaffUserPatch,
)
from app.services import staff_admin_service as svc

router = APIRouter(prefix="/admin", tags=["admin-users"])


def _detail(db: Session, user: StaffUser) -> StaffUserDetail:
    return StaffUserDetail(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        access={} if user.is_admin else svc.access_map(db, user.id),
        created_at=user.created_at,
    )


def _target_or_404(db: Session, user_id: int) -> StaffUser:
    try:
        return svc.get_user(db, user_id)
    except svc.StaffUserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Staff user not found"
        ) from None


def _refuse(
    db: Session, exc: svc.StaffAdminRefused, *, actor: StaffUser, target_id: int, action: str
) -> HTTPException:
    """Audit a refusal and turn it into a 409 carrying its reason.

    409 rather than 403: the caller has the authority, the platform is refusing
    the outcome. A 403 would read as "you may not do this", which would send an
    administrator looking for a permission that is not the problem.

    The body carries a stable `code` alongside the prose. The dashboard ships in
    five languages, so it translates the code and uses `message` only as a
    fallback — returning English prose alone put an English sentence on a Russian
    screen, which no type or test caught.
    """
    svc.audit_refusal(
        db, actor=actor, target_id=target_id, action=action, reason=exc.message
    )
    db.commit()
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get(
    "/pages",
    response_model=PageCatalogOut,
    summary="The grantable dashboard pages, in nav order (admin-only)",
)
def list_pages(_: StaffUser = Depends(require_admin)) -> PageCatalogOut:
    """GET /admin/pages — the vocabulary the access matrix is built from.

    Served rather than hardcoded in the dashboard so a page added to the catalog
    appears in the matrix without a frontend release, and the two cannot drift
    into granting a permission nothing checks.
    """
    return PageCatalogOut.build()


@router.get(
    "/users",
    response_model=list[StaffUserListItem],
    summary="List staff users (admin-only)",
)
def list_staff_users(
    _: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[StaffUserListItem]:
    """GET /admin/users — every staff account.

    Also backs the Assign Owner dropdown on the Purchase Requests detail panel.
    """
    users = db.query(StaffUser).order_by(StaffUser.id).all()
    return [
        StaffUserListItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            is_admin=u.is_admin,
            is_active=u.is_active,
            granted_pages=0 if u.is_admin else len(svc.access_map(db, u.id)),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get(
    "/users/{user_id}",
    response_model=StaffUserDetail,
    summary="One staff user with their access map (admin-only)",
)
def get_staff_user(
    user_id: int,
    _: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """GET /admin/users/{id}."""
    return _detail(db, _target_or_404(db, user_id))


@router.post(
    "/users",
    response_model=StaffUserDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff user (admin-only)",
)
def create_staff_user(
    payload: StaffUserCreate,
    current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """POST /admin/users — create an account and set what it may reach."""
    try:
        user = svc.create_user(
            db,
            actor=current_user,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            is_admin=payload.is_admin,
            access=payload.access,
        )
    except svc.EmailAlreadyUsed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "email_taken",
                "message": "A staff user with this email already exists",
            },
        ) from None
    db.commit()
    db.refresh(user)
    return _detail(db, user)


@router.patch(
    "/users/{user_id}",
    response_model=StaffUserDetail,
    summary="Update a staff user (admin-only)",
)
def patch_staff_user(
    user_id: int,
    payload: StaffUserPatch,
    current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """PATCH /admin/users/{id} — name, administrator flag, or password reset."""
    target = _target_or_404(db, user_id)
    try:
        svc.update_user(
            db,
            actor=current_user,
            target=target,
            full_name=payload.full_name,
            is_admin=payload.is_admin,
            password=payload.password,
        )
    except svc.StaffAdminRefused as exc:
        raise _refuse(
            db, exc, actor=current_user, target_id=user_id, action="staff_user.update"
        ) from None
    db.commit()
    db.refresh(target)
    return _detail(db, target)


@router.put(
    "/users/{user_id}/access",
    response_model=StaffUserDetail,
    summary="Replace a staff user's page access (admin-only)",
)
def set_staff_access(
    user_id: int,
    payload: StaffAccessUpdate,
    current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """PUT /admin/users/{id}/access — the complete map, not a delta."""
    target = _target_or_404(db, user_id)
    try:
        svc.set_access(db, actor=current_user, target=target, access=payload.access)
    except svc.StaffAdminRefused as exc:
        raise _refuse(
            db, exc, actor=current_user, target_id=user_id, action="staff_user.set_access"
        ) from None
    db.commit()
    db.refresh(target)
    return _detail(db, target)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=StaffUserDetail,
    summary="Deactivate a staff user (admin-only)",
)
def deactivate_staff_user(
    user_id: int,
    current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """POST /admin/users/{id}/deactivate — the revocation path.

    Deliberately not a DELETE: `audit_log.staff_user_id` points here, and
    removing the row would detach a person's history from their name.
    """
    target = _target_or_404(db, user_id)
    try:
        svc.set_active(db, actor=current_user, target=target, is_active=False)
    except svc.StaffAdminRefused as exc:
        raise _refuse(
            db, exc, actor=current_user, target_id=user_id, action="staff_user.deactivate"
        ) from None
    db.commit()
    db.refresh(target)
    return _detail(db, target)


@router.post(
    "/users/{user_id}/activate",
    response_model=StaffUserDetail,
    summary="Reactivate a staff user (admin-only)",
)
def activate_staff_user(
    user_id: int,
    current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDetail:
    """POST /admin/users/{id}/activate."""
    target = _target_or_404(db, user_id)
    svc.set_active(db, actor=current_user, target=target, is_active=True)
    db.commit()
    db.refresh(target)
    return _detail(db, target)
