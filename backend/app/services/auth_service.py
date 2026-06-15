"""
Authentication service: validates credentials, issues token pair, manages the refresh cookie.

DEC-auth-split: access token (15 min) in response body; refresh token (7 d) in httpOnly cookie.
T-03-01: generic 401 on any auth failure — never reveal which field (email or password) was wrong.
T-03-05: refresh token in HttpOnly + Secure + SameSite cookie (not JS-readable).
T-03-06: identity derived only from the verified JWT, never from the request body.
"""

from __future__ import annotations

import os

from fastapi import Response
from sqlalchemy.orm import Session

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
_COOKIE_SECURE = os.environ.get("APP_ENV", "development").lower() == "production"


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

    if not verify_password(password, user.password_hash):
        return None

    if not user.is_active:
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
