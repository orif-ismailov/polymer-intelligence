"""Cabinet auth endpoints: login + password under /portal.

- POST /portal/auth/login     → portal_access token (body) + portal_session cookie
- POST /portal/auth/register  → 202, always the same body (an access REQUEST)
- POST /portal/auth/password  → change the password; the only way past the first-login gate
- POST /portal/auth/refresh   → rotate cookie + new access token
- POST /portal/auth/logout    → clear cookie
- GET  /portal/me / PATCH /portal/me

Credentials are issued by staff (`api_admin.py`); nothing here creates an account that
can sign in. Identity comes only from the verified password check or the verified JWT,
never from a request body.

This router mixes anonymous and authenticated routes, so its OpenAPI failure sets are
declared PER ROUTE — a router-level 401 would document a code `register` cannot return.
"""

from __future__ import annotations

from datetime import UTC, datetime

import redis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api import errors
from app.api.deps import get_account_for_password_change, get_current_account
from app.api.portal.deps import get_current_session_family
from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import create_portal_access_token, decode_token
from app.domains.accounts import service as account_service
from app.domains.accounts.models import UserAccount
from app.domains.accounts.schemas import (
    AccountOut,
    LoginIn,
    MeUpdateIn,
    PasswordChangeIn,
    PortalTokenResponse,
    RegisterAccepted,
    RegisterIn,
    StepUpIn,
    StepUpOut,
)
from app.models.enums import AccountStatus
from app.services import rate_limit, session_service
from app.services.audit_service import write_audit
from app.services.auth_service import (
    begin_session,
    clear_portal_session_cookie,
    get_portal_session_cookie_name,
    rotate_session,
    session_http_error,
)

router = APIRouter(prefix="/portal", tags=["portal-auth"])

_PORTAL_COOKIE = get_portal_session_cookie_name()

#: One generic answer for an unknown login, a wrong password, a blocked account and
#: an application that has not been granted credentials. Splitting them would tell a
#: caller which logins exist, which is most of what an attacker came for.
_INVALID_CREDENTIALS = "Invalid credentials"


def _client_ip(request: Request) -> str:
    """Client IP for the per-IP rate caps. Reads X-Real-IP, NEVER X-Forwarded-For.

    This distinction is the whole security of the cap, so it is not a style choice:

    * nginx builds X-Forwarded-For with `$proxy_add_x_forwarded_for`, which APPENDS
      the peer address to whatever the client already sent. So the first entry is
      always caller-supplied — `xff.split(",")[0]` returns an attacker's string, and
      rotating it gives every request its own bucket. That is what this function
      used to do, and it made the per-IP cap decorative: unlimited breadth across
      accounts, billed to a metered account.
    * nginx sets X-Real-IP with `proxy_set_header`, which OVERWRITES. A client-sent
      value cannot survive it. Every `/api` location in all four configs
      (`nginx.conf`, `nginx.dev.conf`, and both `*.behind-proxy.conf`) sets it, and
      in the behind-proxy topology `set_real_ip_from`/`real_ip_header` have already
      resolved `$remote_addr` to the true client before it is copied.

    The fallback is `request.client`, and it is weaker than it looks: uvicorn ships
    `ProxyHeadersMiddleware` ENABLED, so when the socket peer is trusted
    (`--forwarded-allow-ips`, default `127.0.0.1`) uvicorn REWRITES `request.client`
    from X-Forwarded-For — taking the rightmost entry — before this function ever
    runs. Verified live: with no X-Real-IP, requests carrying a forged
    `X-Forwarded-For: 10.0.0.N, 203.0.113.9` all counted into a `203.0.113.9`
    bucket. So on a same-host deployment the fallback can still be caller-influenced.

    Production does not depend on it — every `/api` location in all four nginx
    configs sets X-Real-IP, so the first branch always wins, and the peer there is
    the nginx container (not in uvicorn's default trust list) anyway. Both compose
    files additionally pass `--no-proxy-headers` to switch that rewriting off
    outright: nothing in this app reads `request.url`/`request.scheme`, so the
    middleware's only effect here was to make `request.client` untrustworthy.

    Either way this value only keys a rate-limit bucket, never an authorization
    decision. Nothing that grants access may be built on it without a real
    trusted-proxy check.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _too_many(exc: rate_limit.RateLimited) -> HTTPException:
    """429 with a Retry-After. Deliberately not `portal.deps.rate_limited`, whose
    body says "Daily limit reached" — these are minute-scale windows and that
    sentence would be false on screen."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts",
        headers={"Retry-After": str(exc.retry_after)},
    )


def _token_response(account: UserAccount, fam: str | None = None) -> PortalTokenResponse:
    return PortalTokenResponse(
        access_token=create_portal_access_token(subject=str(account.id), fam=fam),
        account=AccountOut.model_validate(account),
    )


# ── Sign-in ───────────────────────────────────────────────────────────────────


@router.post(
    "/auth/login",
    response_model=PortalTokenResponse,
    responses={
        **errors.error(
            401,
            "Unknown login, wrong password, a blocked account, or an application that "
            "has not been granted credentials — one generic answer for all four, so a "
            "caller cannot learn which logins exist.",
            _INVALID_CREDENTIALS,
        ),
        **errors.error(
            429,
            "Too many attempts, counted per client IP and per login.",
            "Too many attempts",
            headers=errors.RETRY_AFTER_HEADER,
        ),
    },
)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> PortalTokenResponse:
    """Authenticate with the staff-issued credentials; issue a token + session cookie."""
    # IP bucket FIRST: a spray across many logins is capped before it can walk the
    # per-login counters, which on their own would allow limit × logins attempts.
    try:
        rate_limit.enforce_window(
            redis_client,
            "portal_login_ip",
            _client_ip(request),
            rate_limit.PORTAL_LOGIN_PER_IP_PER_MIN,
            60,
        )
        rate_limit.enforce_window(
            redis_client,
            "portal_login",
            body.login,
            rate_limit.PORTAL_LOGIN_PER_ACCOUNT_PER_5MIN,
            300,
        )
    except rate_limit.RateLimited as exc:
        raise _too_many(exc) from exc

    account = account_service.authenticate(db, body.login, body.password)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        )

    db.commit()  # last_login_at
    try:
        fam = begin_session(
            redis_client,
            response,
            kind=session_service.KIND_PORTAL,
            subject_id=account.id,
        )
    except session_service.SessionUnavailable as exc:
        raise session_http_error(exc) from exc
    return _token_response(account, fam)


# ── Registration — an access request, not a sign-up ───────────────────────────


@router.post(
    "/auth/register",
    response_model=RegisterAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **errors.error(
            429,
            "Too many applications from this client IP.",
            "Too many attempts",
            headers=errors.RETRY_AFTER_HEADER,
        ),
    },
)
def register(
    body: RegisterIn,
    request: Request,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> RegisterAccepted:
    """Record an access request. Creates a `pending` account — no token, no cookie.

    202 with a fixed body EVERY time, including for a phone that has applied before:
    the response is the last place that distinction could leak, now that `phone`
    carries no unique constraint to leak it from. A malformed phone is the one
    exception, because it is a form error the applicant can act on.
    """
    try:
        rate_limit.enforce_window(
            redis_client,
            "portal_register_ip",
            _client_ip(request),
            rate_limit.PORTAL_REGISTER_PER_IP_PER_HOUR,
            3600,
        )
        rate_limit.enforce_daily(
            redis_client,
            "portal_register_ip_day",
            _client_ip(request),
            rate_limit.PORTAL_REGISTER_PER_IP_PER_DAY,
        )
    except rate_limit.RateLimited as exc:
        raise _too_many(exc) from exc

    try:
        account = account_service.register(
            db,
            phone=body.phone,
            contact_name=body.contact_name,
            company_name=body.company_name,
            note=body.note,
            applied_as=body.applied_as,
        )
    except account_service.InvalidPhone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid phone number"
        ) from exc

    # No staff actor — the applicant is not a staff user and has no identity here.
    write_audit(
        db=db,
        staff_user_id=None,
        action="portal_account.applied",
        entity="user_accounts",
        entity_id=str(account.id),
        details={"company": account.applied_company_name, "applied_as": account.applied_as},
    )
    db.commit()
    return RegisterAccepted()


# ── First-login password change ───────────────────────────────────────────────


@router.post(
    "/auth/password",
    response_model=PortalTokenResponse,
    responses={
        **errors.PORTAL,
        **errors.error(
            400,
            "The current password did not match.",
            "Current password is incorrect",
        ),
        **errors.error(
            429,
            "Too many change attempts for this account.",
            "Too many attempts",
            headers=errors.RETRY_AFTER_HEADER,
        ),
    },
)
def change_password(
    body: PasswordChangeIn,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    account: UserAccount = Depends(get_account_for_password_change),
    portal_session: str | None = Cookie(default=None, alias=_PORTAL_COOKIE),
) -> PortalTokenResponse:
    """Set a new password — the ONLY route past the `must_change_password` gate.

    It takes the exempt dependency for that reason: `get_current_account` refuses an
    account that still owes a password change, so an endpoint guarded by it could
    never be the place the debt is paid.
    """
    try:
        rate_limit.enforce_window(
            redis_client,
            "portal_password_change",
            account.id,
            rate_limit.PORTAL_PASSWORD_CHANGE_PER_5MIN,
            300,
        )
    except rate_limit.RateLimited as exc:
        raise _too_many(exc) from exc

    try:
        account_service.change_password(
            db, account, current=body.current_password, new=body.new_password
        )
    except account_service.WrongPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        ) from exc

    db.commit()

    # A password change ends the old session and starts a clean one. Revoking first
    # matters: the whole reason someone changes a password in a hurry is that they
    # think somebody else has it, and leaving the previous family alive would let the
    # holder of the old cookie keep refreshing for another 30 days.
    if portal_session:
        try:
            old = decode_token(portal_session, expected_type="portal_refresh")
            old_fam = old.get("fam")
            if isinstance(old_fam, str):
                session_service.revoke(redis_client, old_fam)
        except JWTError:
            pass  # unreadable cookie: nothing to revoke, the new session replaces it

    try:
        fam = begin_session(
            redis_client,
            response,
            kind=session_service.KIND_PORTAL,
            subject_id=account.id,
        )
    except session_service.SessionUnavailable as exc:
        raise session_http_error(exc) from exc
    return _token_response(account, fam)


# ── Session ───────────────────────────────────────────────────────────────────


@router.post(
    "/auth/refresh",
    response_model=PortalTokenResponse,
    responses={
        **errors.error(
            401,
            "The `portal_session` cookie is absent, unreadable, expired, of the wrong "
            "type, or names an account that is gone. The client's move is a fresh sign-in.",
            "Session missing",
        ),
        **errors.error(403, "The account is not `active`.", "Account is blocked"),
    },
)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    portal_session: str | None = Cookie(default=None, alias=_PORTAL_COOKIE),
) -> PortalTokenResponse:
    """Rotate the portal_session cookie and mint a fresh access token.

    Deliberately NOT gated on `must_change_password`: refusing here would strand a
    reloaded tab with an expired access token on the very screen where the debt is
    paid. The flag rides along in the account body instead, and the gate lives on
    every route that does something.
    """
    if not portal_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session missing"
        )
    try:
        payload = decode_token(portal_session, expected_type="portal_refresh")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from exc

    try:
        account_id = int(payload.get("sub"))  # type: ignore[arg-type]
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc

    account: UserAccount | None = (
        db.query(UserAccount).filter(UserAccount.id == account_id).first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found"
        )
    if account.status != AccountStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")

    fam, jti, abs_exp = payload.get("fam"), payload.get("jti"), payload.get("abx")
    if not isinstance(fam, str) or not isinstance(jti, str) or not isinstance(abs_exp, int):
        # A cookie minted before rotation shipped: well-signed, but belonging to no
        # family, so there is nothing to spend. One re-login and it is gone.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    if int(datetime.now(UTC).timestamp()) >= abs_exp:
        session_service.revoke(redis_client, fam)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    try:
        fam = rotate_session(
            redis_client,
            response,
            kind=session_service.KIND_PORTAL,
            subject_id=account.id,
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

    return _token_response(account, fam)


@router.post("/auth/logout")
def logout(
    response: Response,
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    portal_session: str | None = Cookie(default=None, alias=_PORTAL_COOKIE),
) -> dict[str, bool]:
    """End the session: revoke the family, then clear the cookie.

    Revoking is the half that was missing. Clearing a cookie stops this browser from
    presenting the token; it does nothing about a copy taken from it. Now the token
    dies on the server, so logout means what a user assumes it means.

    Stays unauthenticated and always answers ok: an expired access token must never
    be the reason someone cannot end their own session.
    """
    if portal_session:
        try:
            payload = decode_token(portal_session, expected_type="portal_refresh")
            fam = payload.get("fam")
            if isinstance(fam, str):
                session_service.revoke(redis_client, fam)
        except JWTError:
            pass  # unreadable cookie: still clear it

    clear_portal_session_cookie(response)
    return {"ok": True}


@router.post(
    "/auth/step-up",
    response_model=StepUpOut,
    responses={
        **errors.PORTAL,
        **errors.error(
            401,
            "The password did not match, or the session behind the access token is "
            "gone. Same body either way.",
            _INVALID_CREDENTIALS,
        ),
        **errors.error(
            429,
            "Too many step-up attempts for this account.",
            "Too many attempts",
            headers=errors.RETRY_AFTER_HEADER,
        ),
    },
)
def step_up(
    body: StepUpIn,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
    account: UserAccount = Depends(get_current_account),
    fam: str = Depends(get_current_session_family),
) -> StepUpOut:
    """Re-enter the password to unlock sensitive actions for a few minutes.

    The stamp goes on the session family rather than into a token, so it survives a
    refresh mid-flow — a rotation happening while someone fills in a bank form must
    not send them back to the password prompt.

    Rate-limited on the same footing as sign-in: without that, this endpoint is an
    oracle for testing passwords against an already-stolen access token.
    """
    try:
        rate_limit.enforce_window(
            redis_client,
            "portal_step_up",
            account.id,
            rate_limit.PORTAL_PASSWORD_CHANGE_PER_5MIN,
            300,
        )
    except rate_limit.RateLimited as exc:
        raise _too_many(exc) from exc

    if not account_service.verify_account_password(account, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        )

    try:
        session_service.stamp_step_up(redis_client, fam)
    except (session_service.SessionInvalid, session_service.SessionUnavailable) as exc:
        raise session_http_error(exc) from exc

    return StepUpOut(expires_in=settings.STEP_UP_TTL_MINUTES * 60)


# ── Profile ───────────────────────────────────────────────────────────────────


@router.get("/me", response_model=AccountOut, responses=errors.PORTAL)
def get_me(account: UserAccount = Depends(get_account_for_password_change)) -> AccountOut:
    """The caller's own account.

    Exempt from the password-change gate on purpose: after a hard reload the client
    holds nothing but the refresh cookie, and this is where it learns it owes a
    password change. A 403 here would leave it unable to find that out.
    """
    return AccountOut.model_validate(account)


@router.patch("/me", response_model=AccountOut, responses=errors.PORTAL)
def update_me(
    body: MeUpdateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> AccountOut:
    if body.name is not None:
        account.name = body.name
    if body.language is not None:
        account.language = body.language
    db.commit()
    return AccountOut.model_validate(account)
