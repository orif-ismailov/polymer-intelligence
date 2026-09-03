"""
FastAPI dependency providers for authentication and authorization.

DEC-auth-split: Access tokens are short-lived JWTs (15 min) sent as Bearer tokens.
Identity is extracted from the verified JWT, never from the request body (T-03-06, dev-spec §10.5).

Dependencies provided:
- get_current_staff_user: decodes Bearer access token, loads StaffUser, rejects if inactive
- get_current_client: validates Telegram initData HMAC, upserts clients row, returns Client
- require_admin / require_admin_sse: allow only administrators (`staff_users.is_admin`)
- require_page(page, level) / require_page_sse: gate on one dashboard page
- page_access_for: the caller's whole reach, for GET /auth/me

Staff authorization has two layers. `is_admin` grants everything, including pages
added after the account was created; everyone else is granted one dashboard page
at a time (`staff_page_access`, migration 0044) at `read` or `write`, and a page
with no grant cannot be reached. The four-role `staff_role` enum both replaced
(migration 0042) could only be changed with SQL, because nothing but the seeder
ever wrote it.

Every decision reads the staff row and its grants on each request, never a token
claim, so revoking access takes effect on the next request rather than when a
15-minute token expires.
"""

from __future__ import annotations

from collections.abc import Callable

import sqlalchemy as sa
from fastapi import Cookie, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pages import PAGES, AccessLevel, is_page, satisfies
from app.core.security import decode_token
from app.domains.accounts.models import UserAccount
from app.domains.requests.models import Client
from app.models.enums import AccountStatus
from app.models.staff import StaffPageAccess, StaffUser

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


def _assert_admin(current_user: StaffUser) -> StaffUser:
    """Raise 403 unless the user is an administrator. Shared by both guards below."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: administrator only",
        )
    return current_user


def require_admin(
    current_user: StaffUser = Depends(get_current_staff_user),
) -> StaffUser:
    """Allow only administrators.

    Authorization is enforced at the API layer, never the UI (REQ-roles,
    dev-spec §10.5, T-03-04).
    """
    return _assert_admin(current_user)


def require_admin_sse(
    current_user: StaffUser = Depends(get_current_staff_user_sse),
) -> StaffUser:
    """Admin guard for SSE routes.

    Separate from :func:`require_admin` only in what it depends on. `EventSource`
    cannot set an `Authorization` header, so SSE routes accept the token as a
    query param via :func:`get_current_staff_user_sse`; stacking the Bearer-only
    guard on top of them would reject every browser that connects.
    """
    return _assert_admin(current_user)


def _normalize_pages(pages: str | tuple[str, ...]) -> tuple[str, ...]:
    """Validate a page argument at import time.

    A typo would gate the endpoint on a permission nobody can hold. That fails
    closed, which is the safe direction, but it surfaces as a screen that is
    broken for everyone except administrators — so it fails at import instead.
    """
    keys = (pages,) if isinstance(pages, str) else pages
    unknown = [k for k in keys if not is_page(k)]
    if unknown or not keys:
        raise ValueError(f"Unknown dashboard page(s): {unknown or 'none given'}")
    return keys


def _resolve_page_access(
    db: Session, user: StaffUser, pages: tuple[str, ...], level: AccessLevel
) -> StaffUser:
    """Allow `user` through if they hold `level` (or better) on ANY of `pages`.

    Administrators short-circuit: they hold every page, including pages added
    after their account was created. Everyone else is checked against stored
    grants, and no grant means no access — absence is the denial.
    """
    if user.is_admin:
        return user

    granted = dict(
        db.execute(
            sa.select(StaffPageAccess.page, StaffPageAccess.access).where(
                StaffPageAccess.staff_user_id == user.id,
                StaffPageAccess.page.in_(pages),
            )
        ).all()
    )

    if not any(satisfies(granted.get(p), level) for p in pages):
        # Deliberately uniform whether the pages are unknown to this account or
        # merely read-only for them: the 403 body is not the place to enumerate
        # what somebody may not reach.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: requires {level} access to {' or '.join(pages)}",
        )
    return user


def require_page(
    pages: str | tuple[str, ...], level: AccessLevel
) -> Callable[[StaffUser, Session], StaffUser]:
    """Dependency factory gating an endpoint on the dashboard page(s) it serves.

    `pages` is one key from `app.core.pages.PAGES`, or a tuple of them — the same
    vocabulary an administrator grants in, so what they tick on the users screen
    is what the API enforces. Read endpoints take `"read"`, mutations take
    `"write"`, and `write` satisfies `read` (see `pages.satisfies`).

    A TUPLE MEANS "any of", and it is how an endpoint that feeds more than one
    screen is expressed. `GET /feed` backs the live feed, the offers page and the
    dashboard home; gating it on the live feed alone would leave somebody granted
    only the dashboard staring at a permission error on their landing page.

    Authorization is enforced HERE, never in the UI: the dashboard hides pages a
    user cannot reach as a courtesy, but hiding a link is not a permission.

    Usage::

        @router.get("/admin/deals")
        def list_deals(_: StaffUser = Depends(require_page("deals", "read"))):
            ...

        @router.get("/feed")
        def feed(_: StaffUser = Depends(
            require_page(("dashboard", "liveFeed", "offers"), "read")
        )):
            ...
    """
    keys = _normalize_pages(pages)

    def _check_page_access(
        current_user: StaffUser = Depends(get_current_staff_user),
        db: Session = Depends(get_db),
    ) -> StaffUser:
        return _resolve_page_access(db, current_user, keys, level)

    return _check_page_access


def require_page_sse(
    pages: str | tuple[str, ...], level: AccessLevel
) -> Callable[[StaffUser, Session], StaffUser]:
    """The same gate for SSE routes.

    Differs from :func:`require_page` only in what it depends on. `EventSource`
    cannot set an `Authorization` header, so SSE routes take the token as a query
    param via :func:`get_current_staff_user_sse`; stacking the Bearer-only guard
    on one would reject every browser that connects, while every header-based
    test kept passing.
    """
    keys = _normalize_pages(pages)

    def _check_page_access(
        current_user: StaffUser = Depends(get_current_staff_user_sse),
        db: Session = Depends(get_db),
    ) -> StaffUser:
        return _resolve_page_access(db, current_user, keys, level)

    return _check_page_access


def page_access_for(db: Session, user: StaffUser) -> dict[str, str]:
    """Every page this user can reach, as `{page: 'read' | 'write'}`.

    Backs `GET /auth/me`, which is how the dashboard decides what to show. An
    administrator gets the whole catalog at `write` — computed rather than
    stored, so it cannot fall behind a page added later.
    """
    if user.is_admin:
        return {p.key: "write" for p in PAGES}

    rows = db.execute(
        sa.select(StaffPageAccess.page, StaffPageAccess.access).where(
            StaffPageAccess.staff_user_id == user.id
        )
    ).all()
    return {page: access for page, access in rows}


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
        from app.domains.requests.clients import (  # noqa: PLC0415
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
