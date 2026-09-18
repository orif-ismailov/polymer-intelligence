"""Cabinet identity: password sign-in, and registration as an application.

Replaces the phone-OTP rail (`otp.py`, deleted in the same change). Two acts live
here and they are deliberately asymmetric:

* **`authenticate`** answers whether a login and password belong together. It is a
  near-transcription of `auth_service.authenticate` (staff), and it must keep both of
  that function's properties — real KDF work on every miss so the response time says
  nothing, and ONE branch for wrong-password / blocked / pending so the answer says
  nothing either.
* **`register`** records that somebody asked for access. It grants nothing: no
  credentials, no session, `status=pending`. Staff turn an application into an account
  by issuing credentials (`admin_service.issue_credentials`).

`normalize_phone` moved here from `otp.py` unchanged — the registration form still
takes a phone, it is just contact information now rather than identity.
"""

from __future__ import annotations

import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import dummy_verify, hash_password, verify_password
from app.domains.accounts.models import UserAccount
from app.models.enums import AccountStatus

logger = logging.getLogger(__name__)


# ── Domain exceptions (no `Error` suffix — house style, ruff N818 off) ────────


class InvalidPhone(Exception):
    """The supplied phone number is not a valid E.164 number."""


class WrongPassword(Exception):
    """The current password supplied to a self-service change did not match."""


# ── Normalization ─────────────────────────────────────────────────────────────


def normalize_phone(raw: str) -> str:
    """Normalize a phone number to E.164 (`+` + 8–15 digits).

    Uzbek national mobile numbers (9 digits) default to +998; a leading `+` (or
    `00`) international prefix is accepted as-is. Raises `InvalidPhone` on anything
    that isn't a plausible E.164 number.
    """
    cleaned = "".join(ch for ch in raw if ch not in " \t()-. ")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if cleaned.startswith("+"):
        digits = cleaned[1:]
    elif cleaned.startswith("998"):
        digits = cleaned
    elif len(cleaned) == 9 and cleaned.isdigit():
        digits = "998" + cleaned  # bare UZ national mobile
    else:
        digits = cleaned

    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        raise InvalidPhone(f"not a valid phone number (got {len(digits)} digits)")
    return "+" + digits


def normalize_login(raw: str) -> str:
    """Fold a login to its stored form: trimmed and lower-case.

    The unique index is on `lower(login)`, so this is the only shape a lookup may
    use. Applied on BOTH sides — the sign-in body and the staff issue form — because
    an account created as `Ivan` that cannot be signed into as `ivan` is the bug
    `staff_users.email` already paid for once.
    """
    return raw.strip().lower()


# ── Sign-in ───────────────────────────────────────────────────────────────────


def authenticate(db: Session, login: str, password: str) -> UserAccount | None:
    """Return the account for `login`/`password`, or None — never why.

    Two properties, both of which look like redundancy until they are removed:

    * **Every miss does real argon2 work.** An unknown login and an account that has
      no credentials yet both run `dummy_verify`, so neither answers measurably faster
      than a real password check. Without it the timing difference enumerates logins.
    * **Wrong password, blocked and pending share one branch.** Splitting them would
      tell a caller that a login exists and is merely disabled, which is most of what
      an attacker wants to know.
    """
    account: UserAccount | None = (
        db.query(UserAccount)
        .filter(sa.func.lower(UserAccount.login) == normalize_login(login))
        .first()
    )

    if account is None or account.password_hash is None:
        dummy_verify(password)
        return None

    if not verify_password(password, account.password_hash):
        return None
    if account.status != AccountStatus.active:
        return None

    account.last_login_at = datetime.datetime.now(datetime.UTC)
    return account


# ── Registration (an application, not an account) ─────────────────────────────


def register(
    db: Session,
    *,
    phone: str,
    contact_name: str,
    company_name: str,
    note: str | None = None,
    language: str = "ru",
) -> UserAccount:
    """Record an access request as a `pending` account. Grants nothing.

    Raises `InvalidPhone` for an unparseable number — a form error, and the only
    thing this endpoint may ever vary its answer on. Everything else, including a
    phone that has applied before, produces the same row and the same response;
    `phone` carries no unique constraint precisely so the database cannot leak that
    distinction on the endpoint's behalf.

    The caller commits.
    """
    account = UserAccount(
        phone=normalize_phone(phone),
        name=contact_name.strip() or None,
        language=language,
        status=AccountStatus.pending,
        applied_company_name=company_name.strip() or None,
        application_note=(note or "").strip() or None,
    )
    db.add(account)
    db.flush()  # assign id for the audit row; caller commits
    return account


def verify_account_password(account: UserAccount, password: str) -> bool:
    """Whether `password` is this account's current one. No side effects.

    Used by the step-up gate, where the question is "is this still the same person"
    rather than "who is this" — the identity is already settled by the access token,
    and re-running `authenticate` would answer a different question (and touch
    `last_login_at` for something that is not a login).
    """
    if account.password_hash is None:
        return False
    return verify_password(password, account.password_hash)


# ── Self-service password change ──────────────────────────────────────────────


def change_password(db: Session, account: UserAccount, *, current: str, new: str) -> UserAccount:
    """Replace the account's password, clearing `must_change_password`.

    Verifies `current` first, so a borrowed screen cannot become a stolen account.
    An account with no stored hash cannot reach this (it could not have signed in),
    but the check is explicit rather than an assumption about the caller.

    The caller commits.
    """
    if account.password_hash is None or not verify_password(current, account.password_hash):
        raise WrongPassword("current password does not match")

    account.password_hash = hash_password(new)
    account.password_set_at = datetime.datetime.now(datetime.UTC)
    account.must_change_password = False
    return account
