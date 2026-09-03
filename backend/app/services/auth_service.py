"""
Authentication service: validates credentials, issues token pair, manages the refresh cookie.

DEC-auth-split: access token (15 min) in response body; refresh token (7 d) in httpOnly cookie.
T-03-01: generic 401 on any auth failure — never reveal which field (email or password) was wrong.
T-03-05: refresh token in HttpOnly + Secure + SameSite cookie (not JS-readable).
T-03-06: identity derived only from the verified JWT, never from the request body.
"""

from __future__ import annotations

from fastapi import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_refresh_token,
    dummy_verify,
    verify_password,
)
from app.models.staff import StaffUser

# Cookie configuration
_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

# In production (APP_ENV=production), cookies are Secure-only (HTTPS).
# In dev/test environments, Secure is disabled so HTTP TestClient can send cookies.
# T-03-05: production deployments MUST set APP_ENV=production behind TLS (nginx+certbot).
#
# Read through `settings` rather than `os.environ`: this used to be a raw
# `os.environ.get("APP_ENV", "development")`, which put a security-relevant flag
# outside the env contract entirely — absent from `.env.example`, unvalidated,
# and silently satisfied by any typo. `prod`, `Production ` or a missing value
# all meant "not production", and the only symptom was a staff session cookie
# without `Secure` travelling over plain HTTP. `Settings.APP_ENV` is a Literal,
# so those now fail at startup instead.
_COOKIE_SECURE = settings.APP_ENV == "production"


def authenticate(db: Session, email: str, password: str) -> StaffUser | None:
    """Authenticate a staff user by email and argon2-verified password.

    Returns the StaffUser if credentials are valid and the account is active.
    Returns None for any failure — intentionally does not reveal which field was wrong
    (prevents user-enumeration, T-03-01).

    Args:
        db: The active SQLAlchemy session.
        email: The candidate email address.
        password: The candidate plaintext password.

    Returns:
        The authenticated StaffUser, or None on any failure.
    """
    # T-03-08: parameterized SQLAlchemy query — no string-built SQL
    user: StaffUser | None = (
        db.query(StaffUser).filter(StaffUser.email == email).first()
    )

    if user is None:
        # CR-05 / T-03-01: perform real argon2 KDF work so the unknown-user path
        # consumes the same time as the wrong-password path, closing the timing oracle.
        # dummy_verify uses a real precomputed argon2 hash (_DUMMY_HASH from security.py)
        # and swallows the expected VerifyMismatchError — no InvalidHashError risk.
        dummy_verify(password)
        return None

    # WR-03 / CR-05 / T-03-01: run the argon2 KDF unconditionally, then fold the
    # wrong-password and deactivated-account rejections into a single branch. This
    # makes the two failure paths indistinguishable in both response and timing —
    # a correct password against a deactivated account behaves exactly like a wrong
    # password, so an attacker cannot probe which accounts exist or are disabled.
    password_ok = verify_password(password, user.password_hash)
    if not password_ok or not user.is_active:
        return None

    return user


def set_refresh_cookie(response: Response, staff_user_id: int) -> None:
    """Set the httpOnly refresh token cookie on the given response.

    T-03-05: The refresh token is stored in an HttpOnly + Secure + SameSite=lax
    cookie so it is not accessible from JavaScript.

    Args:
        response: The FastAPI Response object to set the cookie on.
        staff_user_id: The staff user's id (used as JWT sub claim).
    """
    refresh_token = create_refresh_token(subject=str(staff_user_id))
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=_COOKIE_SECURE,  # True in production (HTTPS), False in dev/test (HTTP)
        samesite="lax",         # SameSite=lax protects against CSRF on state-changing requests
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/api/v1/auth",    # scope to auth paths only
    )


def clear_refresh_cookie(response: Response) -> None:
    """Clear the httpOnly refresh token cookie (logout).

    Args:
        response: The FastAPI Response object to clear the cookie on.
    """
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth",
    )


def get_refresh_cookie_name() -> str:
    """Return the refresh cookie name (for use in endpoint cookie extraction)."""
    return _REFRESH_COOKIE_NAME


# ── Browser client session (Telegram Login Widget) ─────────────────────────────
# A separate cookie from the staff refresh_token: different name, scoped to the
# webapp API surface only. Holds a client_session JWT (create_client_session_token)
# so browser visitors authed via the Login Widget stay signed in without initData.

_CLIENT_SESSION_COOKIE_NAME = "client_session"
_CLIENT_SESSION_COOKIE_PATH = "/api/v1/webapp"


def set_client_session_cookie(response: Response, telegram_user_id: int) -> None:
    """Set the httpOnly client-session cookie after a successful Login Widget auth.

    Mirrors the staff refresh-cookie security shape (HttpOnly + Secure-in-prod +
    SameSite=lax) but is scoped to /api/v1/webapp so it only rides along with the
    webapp API the browser client actually calls. Same-origin behind nginx, so
    SameSite=lax is correct and sufficient.

    Args:
        response: The FastAPI Response to set the cookie on.
        telegram_user_id: The verified client's telegram_user_id (JWT sub).
    """
    from app.core.config import settings  # noqa: PLC0415
    from app.core.security import create_client_session_token  # noqa: PLC0415

    token = create_client_session_token(subject=str(telegram_user_id))
    response.set_cookie(
        key=_CLIENT_SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.CLIENT_SESSION_TTL_SECONDS,
        path=_CLIENT_SESSION_COOKIE_PATH,
    )


def clear_client_session_cookie(response: Response) -> None:
    """Clear the httpOnly client-session cookie (browser logout)."""
    response.delete_cookie(
        key=_CLIENT_SESSION_COOKIE_NAME,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        path=_CLIENT_SESSION_COOKIE_PATH,
    )


def get_client_session_cookie_name() -> str:
    """Return the client-session cookie name (for endpoint cookie extraction)."""
    return _CLIENT_SESSION_COOKIE_NAME


# ── Portal session (passwordless OTP accounts) ─────────────────────────────────
# httpOnly refresh cookie for the R1 portal, scoped to /api/v1/portal only. Holds a
# portal_refresh JWT; the short-lived portal_access token is returned in the body.

_PORTAL_SESSION_COOKIE_NAME = "portal_session"
_PORTAL_SESSION_COOKIE_PATH = "/api/v1/portal"


def set_portal_session_cookie(response: Response, account_id: int) -> None:
    """Set the httpOnly portal refresh cookie after OTP verify / on refresh rotation.

    Mirrors the staff/client cookie shape (HttpOnly + Secure-in-prod + SameSite=lax),
    scoped to /api/v1/portal so it only rides along with the portal API.

    Args:
        response: The FastAPI Response to set the cookie on.
        account_id: The verified user_accounts.id (JWT sub).
    """
    from app.core.config import settings  # noqa: PLC0415
    from app.core.security import create_portal_refresh_token  # noqa: PLC0415

    token = create_portal_refresh_token(subject=str(account_id))
    response.set_cookie(
        key=_PORTAL_SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.PORTAL_SESSION_TTL_DAYS * 24 * 60 * 60,
        path=_PORTAL_SESSION_COOKIE_PATH,
    )


def clear_portal_session_cookie(response: Response) -> None:
    """Clear the httpOnly portal session cookie (logout)."""
    response.delete_cookie(
        key=_PORTAL_SESSION_COOKIE_NAME,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        path=_PORTAL_SESSION_COOKIE_PATH,
    )


def get_portal_session_cookie_name() -> str:
    """Return the portal session cookie name (for endpoint cookie extraction)."""
    return _PORTAL_SESSION_COOKIE_NAME
