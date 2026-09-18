"""
Auth API endpoints: POST /auth/login, POST /auth/refresh, POST /auth/logout,
GET /auth/me.

DEC-auth-split: access token (15 min) in response body; refresh token in an httpOnly
cookie, rotating, 30-day sliding window under a 90-day absolute cap (IMEX-1).
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

from datetime import UTC, datetime

import redis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api import errors
from app.api.deps import get_current_staff_user, page_access_for
from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, decode_token
from app.models.staff import StaffUser
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.services import session_service
from app.services.audit_service import write_audit
from app.services.auth_service import (
    authenticate,
    begin_session,
    clear_refresh_cookie,
    get_refresh_cookie_name,
    rotate_session,
    session_http_error,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = get_refresh_cookie_name()


@router.post(
    "/login",
    response_model=TokenResponse,
    # Declared per route, not on the router: /logout answers 204 to anyone, so a
    # router-level 401 would document a failure it cannot produce.
    responses={
        **errors.error(
            401,
            "Unknown email, wrong password, or an inactive account — one generic answer "
            "for all three (T-03-01), so a caller cannot learn which addresses exist.",
            "Invalid credentials",
        ),
        **errors.error(
            503,
            "The session store is unreachable, so the sign-in cannot be recorded. A "
            "cookie issued anyway would be refused on its first refresh.",
            "Session store unavailable",
        ),
    },
)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> TokenResponse:
    """Authenticate a staff user and issue a JWT access token + httpOnly refresh cookie.

    On success:
    - Returns 200 with access_token (15 min), token_type, and is_admin in the body.
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

    # Start the refresh-token family and set the httpOnly cookie (T-03-05).
    try:
        fam = begin_session(
            redis_client, response, kind=session_service.KIND_STAFF, subject_id=user.id
        )
    except session_service.SessionUnavailable as exc:
        # Refuse the sign-in rather than issue a session nothing recorded: that
        # cookie would be rejected on its first refresh, which reads as a broken
        # login rather than as the outage it is.
        raise session_http_error(exc) from exc

    # Write audit_log row for the successful login (T-03-07, REQ-nfr-security)
    write_audit(
        db=db,
        staff_user_id=user.id,
        action="auth.login",
        entity="staff_users",
        entity_id=str(user.id),
        details={"is_admin": user.is_admin},
    )
    db.commit()

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), fam=fam),
        is_admin=user.is_admin,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    refresh_token_cookie: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> None:
    """End the staff session: clear the refresh cookie so the browser cannot re-auth.

    The access token lives only in memory, so the *cookie* is the session — without
    this a staff member could not end their own session at all, and closing the tab
    left a 7-day re-auth sitting on a possibly shared workstation.

    Deliberately unauthenticated: an expired access token must not be the reason you
    are stuck signed in, and the cookie is the only thing being revoked. Identity for
    the audit row comes from the cookie's verified `sub` claim (T-03-06), never from
    the request; an absent or unreadable cookie is still a 204 — logout is idempotent
    and must never leave the caller believing they are still signed in.
    """
    staff_user_id: int | None = None
    if refresh_token_cookie is not None:
        try:
            payload = decode_token(refresh_token_cookie, expected_type="refresh")
            subject = payload.get("sub")
            staff_user_id = int(subject) if subject is not None else None
            # Revoke the family, so the session ends on the SERVER too. Before this
            # the cookie was cleared and the token it held stayed valid for the rest
            # of its life — anyone who had copied it stayed signed in, and "log out"
            # protected nobody but the next person at the same keyboard.
            fam = payload.get("fam")
            if isinstance(fam, str):
                session_service.revoke(redis_client, fam)
        except (JWTError, ValueError, TypeError):
            staff_user_id = None  # unreadable cookie: still clear it, just unattributed

    if staff_user_id is not None:
        write_audit(
            db=db,
            staff_user_id=staff_user_id,
            action="auth.logout",
            entity="staff_users",
            entity_id=str(staff_user_id),
            details={},
        )
        db.commit()

    # The Set-Cookie header set here is merged into the 204 FastAPI builds.
    clear_refresh_cookie(response=response)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        **errors.error(
            401,
            "The refresh cookie is absent, unreadable, expired, past its absolute cap, "
            "already spent, of the wrong type, or names a staff row that is gone or "
            "deactivated. The client's move is a fresh login.",
            "Refresh token missing",
        ),
        **errors.error(
            503,
            "The session store is unreachable. Deliberately NOT 401: the session's "
            "fate is unknown, and signing everyone out over a blip is the failure "
            "this distinction exists to prevent.",
            "Session store unavailable",
        ),
    },
)
def refresh_token(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    refresh_token_cookie: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> TokenResponse:
    """Exchange a valid refresh cookie for a new access token AND a new cookie.

    Reads the httpOnly refresh cookie, verifies signature + expiry + type='refresh',
    confirms the session is live and the user still active, then ROTATES: the
    presented token is spent, a successor is issued, and the cookie is replaced.

    Rotation is the part that was missing. This route used to hand back a new access
    token and leave the refresh cookie untouched, so one captured cookie was good for
    its whole life — the thing IMEX-1 is about.

    On success:
    - Returns 200 with a new access_token, and a Set-Cookie carrying the successor.

    On failure (missing, invalid, expired, replayed, or inactive user):
    - Returns 401. If the session store is unreachable: 503, never 401.
    """
    if refresh_token_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    try:
        payload = decode_token(refresh_token_cookie, expected_type="refresh")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: missing subject",
        )

    try:
        staff_user_id = int(subject)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: invalid subject",
        ) from exc

    # Re-load user from DB to confirm still active (is_admin may have changed)
    user: StaffUser | None = (
        db.query(StaffUser).filter(StaffUser.id == staff_user_id).first()
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated",
        )

    fam, jti, abs_exp = payload.get("fam"), payload.get("jti"), payload.get("abx")
    if not isinstance(fam, str) or not isinstance(jti, str) or not isinstance(abs_exp, int):
        # A well-signed cookie from before rotation shipped. It cannot be rotated —
        # there is no family to spend it from — so it ends here and the user signs
        # in again once. Not an error worth explaining to them.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    # The absolute ceiling, checked against the SIGNED claim rather than anything in
    # Redis: this is what a lost session record cannot quietly extend.
    if int(datetime.now(UTC).timestamp()) >= abs_exp:
        session_service.revoke(redis_client, fam)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    try:
        fam = rotate_session(
            redis_client,
            response,
            kind=session_service.KIND_STAFF,
            subject_id=user.id,
            fam=fam,
            jti=jti,
            abs_exp=abs_exp,
        )
    except (
        session_service.SessionInvalid,
        session_service.SessionReused,
        session_service.SessionUnavailable,
    ) as exc:
        raise session_http_error(exc) from exc

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), fam=fam),
        is_admin=user.is_admin,
    )


@router.get("/me", response_model=MeResponse, responses=errors.STAFF)
def me(
    current_user: StaffUser = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Return the authenticated staff user's identity and reach.

    The access token carries no authorization claim and lives in memory only, so
    after a page reload the dashboard has a freshly re-minted token and no idea
    who it belongs to. This is where it asks.

    Reads the staff row rather than the token, so deactivating or demoting
    someone takes effect on their next poll instead of when their token expires.
    """
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_admin=current_user.is_admin,
        access=page_access_for(db, current_user),
    )
