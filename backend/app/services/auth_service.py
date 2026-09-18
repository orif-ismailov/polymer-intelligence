"""
Authentication service: validates credentials, issues token pair, manages the refresh cookie.

DEC-auth-split: access token (15 min) in response body; refresh token (7 d) in httpOnly cookie.
T-03-01: generic 401 on any auth failure — never reveal which field (email or password) was wrong.
T-03-05: refresh token in HttpOnly + Secure + SameSite cookie (not JS-readable).
T-03-06: identity derived only from the verified JWT, never from the request body.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Protocol

import redis
from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    dummy_verify,
    verify_password,
)
from app.models.staff import StaffUser
from app.services import session_service

# Cookie configuration
_REFRESH_COOKIE_NAME = "refresh_token"

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


def set_refresh_cookie(response: Response, token: str, *, max_age: int) -> None:
    """Set the httpOnly refresh token cookie on the given response.

    T-03-05: The refresh token is stored in an HttpOnly + Secure + SameSite=lax
    cookie so it is not accessible from JavaScript.

    Takes the token rather than minting one (IMEX-1): on a rotation that lost the
    race to a concurrent tab, the cookie we must set is the WINNER's successor, not
    the one this request minted. A helper that mints internally cannot express that.

    Args:
        response: The FastAPI Response object to set the cookie on.
        token: The refresh JWT to store.
        max_age: Cookie lifetime in seconds — the session's remaining life, so the
            browser drops the cookie when the server would refuse it anyway.
    """
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,  # True in production (HTTPS), False in dev/test (HTTP)
        samesite="lax",         # SameSite=lax protects against CSRF on state-changing requests
        max_age=max_age,
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


# ── Portal session (cabinet accounts) ──────────────────────────────────────────
# httpOnly refresh cookie for the R1 portal, scoped to /api/v1/portal only. Holds a
# portal_refresh JWT; the short-lived portal_access token is returned in the body.

_PORTAL_SESSION_COOKIE_NAME = "portal_session"
_PORTAL_SESSION_COOKIE_PATH = "/api/v1/portal"


def set_portal_session_cookie(response: Response, token: str, *, max_age: int) -> None:
    """Set the httpOnly portal refresh cookie after sign-in / on refresh rotation.

    Mirrors the staff/client cookie shape (HttpOnly + Secure-in-prod + SameSite=lax),
    scoped to /api/v1/portal so it only rides along with the portal API. Takes the
    token for the same reason `set_refresh_cookie` does.

    Args:
        response: The FastAPI Response to set the cookie on.
        token: The portal refresh JWT to store.
        max_age: Cookie lifetime in seconds (the session's remaining life).
    """
    response.set_cookie(
        key=_PORTAL_SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
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


# ── Refresh-session lifecycle (IMEX-1) ────────────────────────────────────────
# Sign-in, rotation and logout for BOTH password surfaces. One implementation,
# because the two differ only in which minter and which cookie they use — and
# because the last time they were written separately they drifted to different
# session lengths without anyone noticing.


class _RefreshMinter(Protocol):
    """The shape both refresh-token minters share.

    Spelled out rather than `Callable[..., str]` because mypy is strict here and an
    ellipsis is Any in disguise — which would mean a minter with the wrong keywords
    type-checked fine and failed at the first sign-in.
    """

    def __call__(self, subject: str, *, fam: str, jti: str, abs_exp: int) -> str: ...


def _session_config(
    kind: str,
) -> tuple[_RefreshMinter, Callable[[Response, str, int], None]]:
    """The minter and cookie-setter for a surface."""
    from app.core.security import (  # noqa: PLC0415
        create_portal_refresh_token,
        create_refresh_token,
    )

    if kind == session_service.KIND_STAFF:
        return create_refresh_token, lambda r, t, m: set_refresh_cookie(r, t, max_age=m)
    if kind == session_service.KIND_PORTAL:
        return create_portal_refresh_token, lambda r, t, m: set_portal_session_cookie(
            r, t, max_age=m
        )
    raise ValueError(f"unknown session kind: {kind}")


def _remaining(abs_exp: int) -> int:
    """Seconds of session left: the sliding window, or the absolute cap if nearer."""
    from app.core.config import settings  # noqa: PLC0415

    now = int(datetime.datetime.now(datetime.UTC).timestamp())
    return max(1, min(settings.REFRESH_SESSION_TTL_DAYS * 86400, abs_exp - now))


def begin_session(
    redis_client: redis.Redis,  # type: ignore[type-arg]
    response: Response,
    *,
    kind: str,
    subject_id: int,
) -> str:
    """Start a refresh-token family after a verified sign-in; set the cookie.

    Returns the family id, which the caller puts in the access token's `fam` claim
    so a later sensitive action can find its way back to this session.
    """
    from app.core.config import settings  # noqa: PLC0415
    from app.core.security import new_family_id, new_jti  # noqa: PLC0415

    mint, set_cookie = _session_config(kind)
    fam, jti = new_family_id(), new_jti()
    now = int(datetime.datetime.now(datetime.UTC).timestamp())
    abs_exp = now + settings.REFRESH_SESSION_ABSOLUTE_TTL_DAYS * 86400

    # Redis first: a cookie whose family was never recorded is a session that will be
    # refused on its first refresh, which looks to the user like a broken login.
    session_service.start(
        redis_client, kind=kind, subject_id=subject_id, fam=fam, jti=jti, abs_exp=abs_exp
    )
    set_cookie(
        response,
        mint(subject=str(subject_id), fam=fam, jti=jti, abs_exp=abs_exp),
        _remaining(abs_exp),
    )
    return fam


def rotate_session(
    redis_client: redis.Redis,  # type: ignore[type-arg]
    response: Response,
    *,
    kind: str,
    subject_id: int,
    fam: str,
    jti: str,
    abs_exp: int,
) -> str:
    """Spend the presented refresh token, issue its successor, re-set the cookie.

    Raises `session_service.SessionReused` (family already revoked),
    `SessionInvalid` (family gone) or `SessionUnavailable` (Redis down) — the
    routers map those onto 401 / 401 / 503.

    Note the successor is minted BEFORE the claim, because the claim key stores it:
    that is what lets a concurrent tab be handed this exact token instead of a 401.
    If we lose the race, the minted token is simply discarded.
    """
    from app.core.security import new_jti  # noqa: PLC0415

    mint, set_cookie = _session_config(kind)
    successor = mint(
        subject=str(subject_id), fam=fam, jti=(candidate := new_jti()), abs_exp=abs_exp
    )
    result = session_service.rotate(
        redis_client, fam=fam, jti=jti, new_jti=candidate, successor_token=successor
    )
    token = result.token if result.replayed and result.token else successor
    set_cookie(response, token, _remaining(abs_exp))
    return fam


def session_http_error(exc: Exception) -> HTTPException:
    """Map a session failure onto its status code.

    The 503 is the point. Answering 401 when Redis is merely unreachable would sign
    every user on the platform out over an infrastructure blip — turning a session
    hardening into an outage, and training people to expect random logouts.
    """
    if isinstance(exc, session_service.SessionUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session store unavailable",
        )
    if isinstance(exc, session_service.SessionReused):
        # Deliberately the same body as an ordinary expiry. The holder of a replayed
        # token may well be the attacker, and "we detected your theft" is a hint.
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
    )
