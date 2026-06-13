"""
Auth API endpoints: POST /auth/login and POST /auth/refresh.

DEC-auth-split: access token (15 min) in response body; refresh token (7 d) httpOnly cookie.
REQ-nfr-security: all login attempts (success only) write an audit_log row (T-03-07).
T-03-01: generic 401 on any auth failure — never reveal which field was wrong.
T-03-05: refresh token in HttpOnly + Secure + SameSite cookie.
T-03-06: identity from the verified JWT sub claim, never the request body.

NOTE: brute-force / credential-stuffing protection for POST /auth/login (ASVS L1 V2.2.1)
is delivered at the network layer — plan 01-04 adds an nginx limit_req rate limit
(≈10 req/min, burst=5, key=$binary_remote_addr, returning 429).
This endpoint intentionally has no in-app rate limiter to keep plan files disjoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, decode_token
from app.models.staff import StaffUser
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.audit_service import write_audit
from app.services.auth_service import (
    authenticate,
    get_refresh_cookie_name,
    set_refresh_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = get_refresh_cookie_name()


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a staff user and issue a JWT access token + httpOnly refresh cookie.

    On success:
    - Returns 200 with access_token (15 min), token_type, and role in the body.
    - Sets an httpOnly + Secure + SameSite refresh cookie (7 d) via Set-Cookie header.
    - Writes an audit_log row with action='auth.login'.

    On failure:
    - Returns 401 with a generic error (never hints at which field was wrong, T-03-01).
    - Does NOT set a cookie.
    - Does NOT write an audit_log row.

    Identity comes only from the verified password check — the request body supplies
    only credentials, never a user id (T-03-06).
    """
    user: StaffUser | None = authenticate(db=db, email=body.email, password=body.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Set the httpOnly refresh cookie (T-03-05)
    set_refresh_cookie(response=response, staff_user_id=user.id)

    # Write audit_log row for the successful login (T-03-07, REQ-nfr-security)
    write_audit(
        db=db,
        staff_user_id=user.id,
        action="auth.login",
        entity="staff_users",
        entity_id=str(user.id),
        details={"role": user.role.value},
    )
    db.commit()

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), role=user.role.value),
        role=user.role.value,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    db: Session = Depends(get_db),
    refresh_token_cookie: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> TokenResponse:
    """Exchange a valid refresh cookie for a new access token.

    Reads the httpOnly refresh cookie, verifies signature + expiry + type='refresh',
    confirms the user is still active, and returns a new access token.

    On success:
    - Returns 200 with a new access_token in the body.

    On failure (missing, invalid, expired cookie, or inactive user):
    - Returns 401.
    """
    if refresh_token_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    try:
        payload = decode_token(refresh_token_cookie, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: missing subject",
        )

    try:
        staff_user_id = int(subject)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: invalid subject",
        )

    # Re-load user from DB to confirm still active (role may have changed)
    user: StaffUser | None = (
        db.query(StaffUser).filter(StaffUser.id == staff_user_id).first()
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated",
        )

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), role=user.role.value),
        role=user.role.value,
    )
