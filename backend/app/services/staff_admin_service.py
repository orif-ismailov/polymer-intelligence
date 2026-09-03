"""
Staff administration — create, edit, deactivate colleagues and set their reach.

Before this existed, `StaffUser(...)` was constructed in exactly one place in the
whole backend (`app/seed/seed_staff.py`) and `/admin/users` had a single GET.
Promoting somebody meant running SQL against production, and there was no way at
all to revoke access for someone who left.

TWO GUARDS KEEP THE DOOR OPEN. Fully dynamic access with no floor is how you lock
yourself out of your own dashboard, and no endpoint can let you back in:

  * the LAST active administrator cannot be demoted or deactivated, and
  * you cannot demote or deactivate YOURSELF — the common way to reach the first
    case by accident, and the one where the person who could undo it is the
    person who just lost the ability to.

Both refusals are audited. A refused privileged action is exactly as interesting
as a successful one when reconstructing what happened.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.staff import StaffPageAccess, StaffUser
from app.services.audit_service import write_audit


class StaffAdminRefused(Exception):
    """A staff-administration action was refused (409).

    Carries a stable `code` as well as English prose. The dashboard renders these
    to a person in one of five languages, so the wire has to say WHICH refusal
    happened rather than only describing it — a translated UI showing an English
    sentence is a bug the type checker cannot see.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EmailAlreadyUsed(Exception):
    """A staff account with this email already exists."""


class StaffUserNotFound(Exception):
    """No staff account with this id."""


def get_user(db: Session, user_id: int) -> StaffUser:
    user = db.get(StaffUser, user_id)
    if user is None:
        raise StaffUserNotFound(str(user_id))
    return user


def _active_admin_count(db: Session, *, excluding: int | None = None) -> int:
    stmt = sa.select(sa.func.count()).select_from(StaffUser).where(
        StaffUser.is_admin.is_(True), StaffUser.is_active.is_(True)
    )
    if excluding is not None:
        stmt = stmt.where(StaffUser.id != excluding)
    return int(db.execute(stmt).scalar_one())


def _guard_still_administrable(
    db: Session, *, actor: StaffUser, target: StaffUser, action: str
) -> None:
    """Refuse a change that would leave nobody able to administer the platform.

    Called before demoting or deactivating. Only meaningful when `target` is
    currently an active administrator — removing anyone else's access can always
    be undone by an administrator who still exists.
    """
    if not (target.is_admin and target.is_active):
        return

    if target.id == actor.id:
        raise StaffAdminRefused(
            "self_demote",
            "You cannot remove your own administrator access. "
            "Ask another administrator to do it.",
        )

    if _active_admin_count(db, excluding=target.id) == 0:
        raise StaffAdminRefused(
            "last_admin",
            f"Cannot {action} the last active administrator — "
            "the dashboard would have nobody able to administer it.",
        )


def _replace_access(db: Session, user: StaffUser, access: dict[str, str]) -> None:
    """Make `user`'s grants exactly `access`.

    Delete-then-insert rather than a diff: the screen submits every page it
    rendered, so the map IS the desired state, and a diff would be a second
    place for the two to disagree. Only granted pages are stored — a page absent
    from the map is a page with no row, which is how "no access" is spelled.
    """
    db.execute(
        sa.delete(StaffPageAccess).where(StaffPageAccess.staff_user_id == user.id)
    )
    for page, level in sorted(access.items()):
        db.add(StaffPageAccess(staff_user_id=user.id, page=page, access=level))


def access_map(db: Session, user_id: int) -> dict[str, str]:
    """This user's stored grants as `{page: level}` (empty for an administrator)."""
    rows = db.execute(
        sa.select(StaffPageAccess.page, StaffPageAccess.access).where(
            StaffPageAccess.staff_user_id == user_id
        )
    ).all()
    return {page: access for page, access in rows}


def create_user(
    db: Session,
    *,
    actor: StaffUser,
    email: str,
    full_name: str,
    password: str,
    is_admin: bool,
    access: dict[str, str],
) -> StaffUser:
    """Create a staff account. The caller must already be an administrator."""
    exists = db.execute(
        sa.select(StaffUser.id).where(StaffUser.email == email)
    ).scalar_one_or_none()
    if exists is not None:
        raise EmailAlreadyUsed(email)

    user = StaffUser(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.flush()  # need the id before the grants reference it

    # An administrator holds every page implicitly, so storing grants for one
    # would be rows nothing reads that go stale the moment a page is added.
    if not is_admin:
        _replace_access(db, user, access)

    write_audit(
        db=db,
        staff_user_id=actor.id,
        action="staff_user.create",
        entity="staff_users",
        entity_id=str(user.id),
        details={
            "email": email,
            "is_admin": is_admin,
            "granted_pages": sorted(access) if not is_admin else "all",
        },
    )
    return user


def update_user(
    db: Session,
    *,
    actor: StaffUser,
    target: StaffUser,
    full_name: str | None,
    is_admin: bool | None,
    password: str | None,
) -> StaffUser:
    """Apply a partial update. Omitted fields are left alone."""
    changed: dict[str, object] = {}

    if is_admin is not None and is_admin != target.is_admin:
        if not is_admin:
            _guard_still_administrable(
                db, actor=actor, target=target, action="demote"
            )
            # Dropping to non-administrator means the page matrix starts
            # applying, and it is empty until somebody fills it in. That is the
            # safe direction: no silent inheritance of what admin implied.
        target.is_admin = is_admin
        changed["is_admin"] = is_admin

    if full_name is not None and full_name != target.full_name:
        target.full_name = full_name
        changed["full_name"] = full_name

    if password is not None:
        target.password_hash = hash_password(password)
        # The FACT of a reset, never the value — not even the hash. S105 flags the
        # literal as a possible credential; it is the audit verb, not a secret.
        changed["password_reset"] = True

    if changed:
        write_audit(
            db=db,
            staff_user_id=actor.id,
            action="staff_user.update",
            entity="staff_users",
            entity_id=str(target.id),
            details=changed,
        )
    return target


def set_access(
    db: Session, *, actor: StaffUser, target: StaffUser, access: dict[str, str]
) -> dict[str, str]:
    """Replace `target`'s page grants wholesale."""
    if target.is_admin:
        raise StaffAdminRefused(
            "admin_holds_all_pages",
            "This account is an administrator and already reaches every page. "
            "Remove administrator access first to grant pages individually.",
        )

    _replace_access(db, target, access)
    write_audit(
        db=db,
        staff_user_id=actor.id,
        action="staff_user.set_access",
        entity="staff_users",
        entity_id=str(target.id),
        details={"access": dict(sorted(access.items()))},
    )
    return access


def set_active(
    db: Session, *, actor: StaffUser, target: StaffUser, is_active: bool
) -> StaffUser:
    """Activate or deactivate an account.

    Deactivation is the revocation path: `deps._resolve_staff_user` already
    refuses an inactive account on the next request, so it takes effect without
    waiting out an unexpired token.
    """
    if not is_active:
        _guard_still_administrable(
            db, actor=actor, target=target, action="deactivate"
        )

    if target.is_active != is_active:
        target.is_active = is_active
        write_audit(
            db=db,
            staff_user_id=actor.id,
            action="staff_user.activate" if is_active else "staff_user.deactivate",
            entity="staff_users",
            entity_id=str(target.id),
            details={"email": target.email},
        )
    return target


def audit_refusal(
    db: Session, *, actor: StaffUser, target_id: int, action: str, reason: str
) -> None:
    """Record a privileged action that was refused.

    A refusal is as interesting as a success when reconstructing what happened —
    "who tried to remove the last administrator" is a question worth being able
    to answer.
    """
    write_audit(
        db=db,
        staff_user_id=actor.id,
        action=f"{action}.refused",
        entity="staff_users",
        entity_id=str(target_id),
        details={"reason": reason},
    )
