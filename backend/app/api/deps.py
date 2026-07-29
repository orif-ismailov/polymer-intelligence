"""
FastAPI dependency providers for authentication and authorization.

DEC-auth-split: Access tokens are short-lived JWTs (15 min) sent as Bearer tokens.
Identity is extracted from the verified JWT, never from the request body (T-03-06, dev-spec §10.5).

Dependencies provided:
- get_current_staff_user: decodes Bearer access token, loads StaffUser, rejects if inactive
- get_current_client: validates Telegram initData HMAC, upserts clients row, returns Client
- require_role(*roles): dependency factory enforcing role membership from the token's role claim
- require_admin: convenience shorthand for require_role(StaffRole.admin)
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Cookie, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models.accounts import UserAccount
from app.models.enums import AccountStatus, StaffRole
from app.models.requests import Client
from app.models.staff import StaffUser

# HTTP Bearer token extractor — auto_error=False so we can return 401 (not 403) on missing header
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_staff_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Extract and verify the Bearer access token, load the staff user.

    Raises HTTP 401 if:
    - No Authorization header is present
    - The token is missing, malformed, expired, or has an invalid signature
    - The token type is not 'access' (rejects refresh tokens used as access tokens)
    - The staff_user no longer exists in the database

    Raises HTTP 403 if:
    - The staff_user account is inactive (is_active=False)

    Returns:
        The authenticated StaffUser ORM object.
    """
    token = credentials.credentials if credentials is not None else None
    return _resolve_staff_user(token, db)


def get_current_staff_user_sse(
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Staff auth for EventSource (SSE) endpoints.

    The browser ``EventSource`` API cannot set an ``Authorization`` header, so
    for SSE routes the short-lived access JWT may instead be supplied as the
    ``access_token`` query parameter. The ``Authorization`` header is still
    preferred when present (e.g. for curl / tests). Verification, identity
    extraction, and active-user checks are identical to
    :func:`get_current_staff_user` (same 401/403 semantics).
    """
    token = credentials.credentials if credentials is not None else access_token
    return _resolve_staff_user(token, db)


def _resolve_staff_user(token: str | None, db: Session) -> StaffUser:
    """Verify an access JWT string and load the active staff user it identifies.

    Shared core of :func:`get_current_staff_user` (Bearer header) and
    :func:`get_current_staff_user_sse` (header or query param). Centralising the
    logic keeps the 401/403 behaviour identical across both entry points.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token, expected_type="access")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Extract the subject (staff_user id) from the verified token
    # T-03-06: identity comes ONLY from the verified token, never from the body
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        staff_user_id = int(subject)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: invalid subject format",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Load the user from DB to confirm they still exist and check is_active
    user: StaffUser | None = (
        db.query(StaffUser).filter(StaffUser.id == staff_user_id).first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> UserAccount:
    """Authenticate a portal person via the Bearer `portal_access` token.

    Audience-isolated from staff/webapp identities: the token type must be
    `portal_access`, so a staff `access` or webapp `client_session` token fails
    here (and a portal token fails on those deps).

    Raises HTTP 401 if the header/token is missing, malformed, expired, the wrong
    type, or the account no longer exists. Raises HTTP 403 if the account is
    blocked (status != active).

    Returns:
        The authenticated UserAccount ORM object.
    """
    token = credentials.credentials if credentials is not None else None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token, expected_type="portal_access")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = payload.get("sub")
    try:
        account_id = int(subject)  # type: ignore[arg-type]  # None/str → caught below
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    account: UserAccount | None = (
        db.query(UserAccount).filter(UserAccount.id == account_id).first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if account.status != AccountStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    return account


def require_role(*roles: StaffRole) -> Callable[[StaffUser], StaffUser]:
    """Dependency factory that enforces role-based access control.

    Creates a FastAPI dependency that checks the current user's role against
    the allowed set. Authorization is enforced at the API layer, never the UI
    (REQ-roles, dev-spec §10.5, T-03-04).

    Args:
        *roles: The allowed StaffRole values for this endpoint.

    Returns:
        A dependency callable that returns the current user if authorized,
        or raises HTTP 403 if their role is not in the allowed set.

    Usage::

        @router.get("/admin/users")
        def list_users(current_user: StaffUser = Depends(require_role(StaffRole.admin))):
            ...
    """

    def _check_role(
        current_user: StaffUser = Depends(get_current_staff_user),
    ) -> StaffUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: requires one of {[r.value for r in roles]}",
            )
        return current_user

    return _check_role


# ── Convenience shortcuts ──────────────────────────────────────────────────────

#: Dependency that allows only admin users.
require_admin = require_role(StaffRole.admin)

#: Dependency that allows analyst and admin users.
require_analyst_or_admin = require_role(StaffRole.analyst, StaffRole.admin)


def _client_from_session_cookie(db: Session, token: str) -> Client | None:
    """Resolve a Client from a browser ``client_session`` JWT cookie.

    Returns the Client if the token is a valid, unexpired client_session whose
    subject maps to an existing clients row; None on any failure (bad signature,
    wrong type, expired, unknown client). Callers translate None into the generic
    401 so no failure detail leaks (T-03-03).
    """
    try:
        payload = decode_token(token, expected_type="client_session")
    except JWTError:
        return None
    try:
        telegram_user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    client: Client | None = (
        db.query(Client).filter(Client.telegram_user_id == telegram_user_id).first()
    )
    return client


def get_current_client(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    client_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Client:
    """Authenticate a webapp client via Telegram initData (Mini App) OR a browser session.

    Two independent verified identity paths — the first that succeeds wins:

    Path A — Telegram Mini App: the ``X-Telegram-Init-Data`` header (initData HMAC,
    dev-spec §3.2). Behaviour is unchanged from the initData-only implementation: a
    present-but-invalid header still yields the generic 401 (it does NOT fall through
    to the cookie). An empty/absent header falls through to Path B.

    Path B — Browser (Telegram Login Widget): the httpOnly ``client_session`` cookie
    issued by POST /webapp/auth/telegram. Verified via decode_token(..., "client_session").

    T-03-01: HMAC verified via hmac.compare_digest (constant-time).
    T-03-02: auth_date TTL enforced; identity read only from the verified payload/token.
    T-03-03: generic 401 "Authentication required" for every failure path —
             never reveals which check failed.
    T-03-06 equivalent: identity derived from verified initData/JWT, never request body.

    Raises:
        HTTPException 401: "Authentication required" when neither path authenticates.

    Returns:
        The authenticated Client ORM object.
    """
    # ── Path A: Telegram Mini App initData (unchanged behaviour) ───────────────
    # A truthy header selects this path; an empty string (sent by the browser client)
    # is treated as absent so it falls through to the cookie path.
    if x_telegram_init_data:
        from app.services.client_service import (  # noqa: PLC0415
            InvalidInitData,
            get_or_create_client,  # noqa: PLC0415
            verify_init_data,
        )

        try:
            payload = verify_init_data(x_telegram_init_data)
        except (InvalidInitData, ValueError):
            # Generic 401 — never reveal which check failed (T-03-03)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            ) from None

        # Extract identity from verified payload ONLY (T-03-06 equivalent)
        user_info = payload.get("user")
        if not isinstance(user_info, dict):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        try:
            telegram_user_id = int(user_info["id"])
        except (KeyError, ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            ) from None

        language_code: str = str(user_info.get("language_code", "ru"))

        client = get_or_create_client(
            db=db,
            telegram_user_id=telegram_user_id,
            language=language_code,
        )
        db.commit()  # The dependency owns the upsert transaction
        return client

    # ── Path B: browser client-session cookie (Telegram Login Widget) ──────────
    if client_session:
        client = _client_from_session_cookie(db, client_session)
        if client is not None:
            return client

    # Neither path authenticated → generic 401 (T-03-03)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
