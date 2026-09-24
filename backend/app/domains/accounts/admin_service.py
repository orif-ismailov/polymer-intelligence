"""Staff administration of cabinet accounts — the door credentials come through.

Registration (`service.register`) produces an application and nothing else. This is
where somebody decides to let a person in: a login, a password, and a `pending` row
becoming `active`. It mirrors `app/services/staff_admin_service.py` because it is the
same act one audience over, and that file's shape is already the reviewed answer to
"an administrator hands out access with no email infrastructure to send it through".

**The plaintext password exists exactly once, in the response to the call that made
it.** We store an argon2 hash, so there is no endpoint that can show it again and no
recovery but regenerating. It is therefore never logged, never written to the audit
`details`, and never returned by a read route — the audit records THAT credentials
were issued, the way `staff_admin_service` records `password_reset: True`.

Every issue and every regenerate sets `must_change_password`. That is not a policy
knob: the issued password is printed in a contract, so it is an initial secret by
construction, and the flag is what keeps it one.
"""

from __future__ import annotations

import datetime
import secrets

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domains.accounts.models import UserAccount
from app.domains.accounts.service import normalize_login
from app.models.enums import AccountStatus
from app.models.staff import StaffUser
from app.services.audit_service import write_audit


class PortalAdminRefused(Exception):
    """A cabinet-account administration action was refused (409).

    Carries a stable `code` as well as English prose, for the reason
    `StaffAdminRefused` does: the dashboard renders refusals in five languages, so
    the wire has to say WHICH refusal happened rather than only describe it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AccountNotFound(Exception):
    """No cabinet account with this id."""


#: No `0/O/1/l/I`. This password is read off a printed contract and typed by hand, and
#: a character somebody cannot transcribe turns into a support call that looks like a
#: broken login. Length carries the entropy instead: 16 chars from a 54-symbol alphabet
#: is ~92 bits, well past anything the 10-attempts-per-5-minutes cap has to survive.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
_GENERATED_LENGTH = 16


def generate_password() -> str:
    """A password staff can hand over on paper. `secrets`, never `random`."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_GENERATED_LENGTH))


def get_account(db: Session, account_id: int) -> UserAccount:
    account = db.get(UserAccount, account_id)
    if account is None:
        raise AccountNotFound(str(account_id))
    return account


def list_accounts(
    db: Session,
    *,
    status: AccountStatus | None = None,
    q: str | None = None,
    applied_as: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UserAccount]:
    """The queue. `status=pending` is the applications waiting for a decision."""
    stmt = sa.select(UserAccount)
    if status is not None:
        stmt = stmt.where(UserAccount.status == status)
    if applied_as is not None:
        stmt = stmt.where(UserAccount.applied_as == applied_as)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            sa.or_(
                UserAccount.name.ilike(like),
                UserAccount.phone.ilike(like),
                UserAccount.login.ilike(like),
                UserAccount.applied_company_name.ilike(like),
            )
        )
    stmt = stmt.order_by(UserAccount.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def _assert_login_free(db: Session, login: str, *, exclude_id: int | None = None) -> None:
    """Refuse a taken login before the unique index does.

    The index (`lower(login)`, partial) is the real guarantee; this check is what
    turns its IntegrityError into a 409 the dashboard can translate, instead of a 500
    somebody has to read a Postgres log to understand.
    """
    stmt = sa.select(UserAccount.id).where(sa.func.lower(UserAccount.login) == login)
    if exclude_id is not None:
        stmt = stmt.where(UserAccount.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise PortalAdminRefused("login_taken", f"Login {login!r} is already in use")


def issue_credentials(
    db: Session,
    *,
    actor: StaffUser,
    target: UserAccount,
    login: str,
    password: str,
) -> str:
    """Give an account a login and a password; return the PLAINTEXT, once.

    Returning the password rather than storing it anywhere readable is the whole
    contract: the caller shows it to the staff member and it is then unrecoverable.

    Sets `status=active` — this IS the decision the application was waiting for —
    and `must_change_password`, because what staff hand over is written down.
    """
    folded = normalize_login(login)
    if not folded:
        raise PortalAdminRefused("login_required", "A login is required")
    _assert_login_free(db, folded, exclude_id=target.id)

    now = datetime.datetime.now(datetime.UTC)
    target.login = folded
    target.password_hash = hash_password(password)
    target.must_change_password = True
    target.password_set_at = now
    target.credentials_issued_at = now
    target.credentials_issued_by = actor.id
    target.status = AccountStatus.active

    write_audit(
        db=db,
        staff_user_id=actor.id,
        action="portal_account.credentials_issued",
        entity="user_accounts",
        entity_id=str(target.id),
        # The login is an identifier and belongs in the record. The password is not
        # here in any form — not the value, not the hash, not its length.
        details={"login": folded},
    )
    return password


def regenerate_password(
    db: Session, *, actor: StaffUser, target: UserAccount, password: str
) -> str:
    """Replace the password; return the PLAINTEXT, once. Same one-read contract."""
    if target.login is None:
        raise PortalAdminRefused(
            "no_credentials", "This account has no login yet — issue credentials first"
        )

    target.password_hash = hash_password(password)
    target.must_change_password = True
    target.password_set_at = datetime.datetime.now(datetime.UTC)

    write_audit(
        db=db,
        staff_user_id=actor.id,
        action="portal_account.password_reset",
        entity="user_accounts",
        entity_id=str(target.id),
        details={"password_reset": True},
    )
    return password


def set_status(
    db: Session, *, actor: StaffUser, target: UserAccount, status: AccountStatus
) -> UserAccount:
    """Block or unblock an account.

    `active` is refused for an account with no credentials: it would be a person the
    system considers cleared to act who cannot sign in, and the only way back is the
    issue flow anyway.
    """
    if status == AccountStatus.active and target.password_hash is None:
        raise PortalAdminRefused(
            "no_credentials", "This account has no credentials — issue them instead"
        )
    if status == target.status:
        return target

    target.status = status
    write_audit(
        db=db,
        staff_user_id=actor.id,
        action=f"portal_account.{status.value}",
        entity="user_accounts",
        entity_id=str(target.id),
        details={"status": status.value},
    )
    return target


def audit_refusal(
    db: Session, *, actor: StaffUser, target_id: int, action: str, code: str
) -> None:
    """Record a refused privileged action.

    A refusal is exactly as interesting as a success when reconstructing what
    happened — someone repeatedly failing to issue credentials for a login they do
    not own is the shape of an attempt, and an empty log is the shape of nothing.
    """
    write_audit(
        db=db,
        staff_user_id=actor.id,
        action=f"{action}.refused",
        entity="user_accounts",
        entity_id=str(target_id),
        details={"code": code},
    )
