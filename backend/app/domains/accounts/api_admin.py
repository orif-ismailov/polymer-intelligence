"""Staff surface for cabinet accounts: the applications queue and credential issuing.

`require_admin` on every route, deliberately NOT a grantable page — the argument
`app/core/pages.py` makes about `adminUsers` applies here word for word: whoever can
mint a cabinet credential can sign in as a customer and act inside their company, so
this is authority being handed out, and nothing that hands out authority may itself
be handed out.

Two routes return a plaintext password. They are the ONLY place it exists — the
account stores an argon2 hash — so the response is the staff member's one chance to
copy it, and regenerating is the only recovery.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.domains.accounts import admin_service as svc
from app.domains.accounts.models import UserAccount
from app.domains.accounts.schemas import (
    AppliedAs,
    IssueCredentialsIn,
    IssuedCredentialsOut,
    PortalAccountOut,
    RegeneratePasswordIn,
)
from app.models.enums import AccountStatus
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin", tags=["admin-portal-accounts"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _target_or_404(db: Session, account_id: int) -> UserAccount:
    try:
        return svc.get_account(db, account_id)
    except svc.AccountNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        ) from None


def _refuse(
    db: Session,
    exc: svc.PortalAdminRefused,
    *,
    actor: StaffUser,
    target_id: int,
    action: str,
) -> HTTPException:
    """Audit a refusal and turn it into a 409 carrying its reason.

    409 rather than 403 for the reason `admin_users._refuse` gives: the caller has
    the authority, the platform is refusing the outcome, and a 403 would send an
    administrator hunting for a permission that is not the problem. The body carries
    a stable `code` because the dashboard translates it into five languages.
    """
    svc.audit_refusal(db, actor=actor, target_id=target_id, action=action, code=exc.code)
    db.commit()
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": exc.message},
    )


# ── routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/portal-accounts",
    response_model=list[PortalAccountOut],
    summary="Cabinet accounts and applications (admin-only)",
)
def list_portal_accounts(
    _: StaffUser = Depends(require_admin),
    account_status: AccountStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    applied_as: AppliedAs | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[PortalAccountOut]:
    """`?status=pending` is the queue of people waiting for a decision;
    `?applied_as=technologist` narrows it to private experts."""
    accounts = svc.list_accounts(
        db, status=account_status, q=q, applied_as=applied_as, limit=limit, offset=offset
    )
    return [PortalAccountOut.model_validate(a) for a in accounts]


@router.get(
    "/portal-accounts/{account_id}",
    response_model=PortalAccountOut,
    summary="One cabinet account (admin-only)",
)
def get_portal_account(
    account_id: int,
    _: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalAccountOut:
    return PortalAccountOut.model_validate(_target_or_404(db, account_id))


@router.post(
    "/portal-accounts/{account_id}/credentials",
    response_model=IssuedCredentialsOut,
    summary="Issue a login + password (admin-only; the password is shown ONCE)",
)
def issue_credentials(
    account_id: int,
    body: IssueCredentialsIn,
    actor: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> IssuedCredentialsOut:
    """Turn an application into an account. Activates it and forces a first change."""
    target = _target_or_404(db, account_id)
    password = body.password or svc.generate_password()
    try:
        plaintext = svc.issue_credentials(
            db, actor=actor, target=target, login=body.login, password=password
        )
    except svc.PortalAdminRefused as exc:
        raise _refuse(
            db, exc, actor=actor, target_id=account_id, action="portal_account.credentials_issued"
        ) from exc

    db.commit()
    return IssuedCredentialsOut(
        account=PortalAccountOut.model_validate(target),
        login=target.login or "",
        password=plaintext,
    )


@router.post(
    "/portal-accounts/{account_id}/password",
    response_model=IssuedCredentialsOut,
    summary="Regenerate the password (admin-only; shown ONCE)",
)
def regenerate_password(
    account_id: int,
    body: RegeneratePasswordIn,
    actor: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> IssuedCredentialsOut:
    target = _target_or_404(db, account_id)
    password = body.password or svc.generate_password()
    try:
        plaintext = svc.regenerate_password(db, actor=actor, target=target, password=password)
    except svc.PortalAdminRefused as exc:
        raise _refuse(
            db, exc, actor=actor, target_id=account_id, action="portal_account.password_reset"
        ) from exc

    db.commit()
    return IssuedCredentialsOut(
        account=PortalAccountOut.model_validate(target),
        login=target.login or "",
        password=plaintext,
    )


@router.post(
    "/portal-accounts/{account_id}/block",
    response_model=PortalAccountOut,
    summary="Block a cabinet account (admin-only)",
)
def block_account(
    account_id: int,
    actor: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalAccountOut:
    """Revocation, deliberately not a DELETE: the person's contracts, offers and
    membership rows stay exactly where they are, and only the door closes."""
    target = _target_or_404(db, account_id)
    svc.set_status(db, actor=actor, target=target, status=AccountStatus.blocked)
    db.commit()
    return PortalAccountOut.model_validate(target)


@router.post(
    "/portal-accounts/{account_id}/unblock",
    response_model=PortalAccountOut,
    summary="Unblock a cabinet account (admin-only)",
)
def unblock_account(
    account_id: int,
    actor: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalAccountOut:
    target = _target_or_404(db, account_id)
    try:
        svc.set_status(db, actor=actor, target=target, status=AccountStatus.active)
    except svc.PortalAdminRefused as exc:
        raise _refuse(
            db, exc, actor=actor, target_id=account_id, action="portal_account.active"
        ) from exc
    db.commit()
    return PortalAccountOut.model_validate(target)
