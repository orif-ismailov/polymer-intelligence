"""Portal auth endpoints (R1 W3 — T3.3): passwordless SMS-OTP under /portal.

- POST /portal/auth/otp/request  → 204 (or 429 with Retry-After)
- POST /portal/auth/otp/verify   → portal_access token (body) + portal_session cookie
- POST /portal/auth/refresh      → rotate cookie + new access token
- POST /portal/auth/logout       → clear cookie
- GET  /portal/me / PATCH /portal/me

Identity comes only from the verified OTP / JWT (never the body). Failures are
uniform so a caller can't distinguish known vs unknown phones.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import create_portal_access_token, decode_token
from app.domains.accounts.models import UserAccount
from app.domains.accounts.otp import (
    InvalidPhone,
    OtpInvalid,
    OtpLocked,
    OtpRateLimited,
    normalize_phone,
    peek_key,
    request_code,
    verify_code,
)
from app.domains.accounts.schemas import (
    AccountOut,
    MeUpdateIn,
    OtpRequestIn,
    OtpVerifyIn,
    PortalTokenResponse,
)
from app.models.enums import AccountStatus
from app.services.auth_service import (
    clear_portal_session_cookie,
    get_portal_session_cookie_name,
    set_portal_session_cookie,
)

router = APIRouter(prefix="/portal", tags=["portal-auth"])

_PORTAL_COOKIE = get_portal_session_cookie_name()


def _client_ip(request: Request) -> str:
    """Client IP for the per-IP OTP cap. Reads X-Real-IP, NEVER X-Forwarded-For.

    This distinction is the whole security of the cap, so it is not a style choice:

    * nginx builds X-Forwarded-For with `$proxy_add_x_forwarded_for`, which APPENDS
      the peer address to whatever the client already sent. So the first entry is
      always caller-supplied — `xff.split(",")[0]` returns an attacker's string, and
      rotating it gives every request its own bucket. That is what this function
      used to do, and it made `_day_ip_key` decorative: unlimited OTP breadth across
      phone numbers, billed to a metered SMS account.
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


def _token_response(account: UserAccount) -> PortalTokenResponse:
    return PortalTokenResponse(
        access_token=create_portal_access_token(subject=str(account.id)),
        account=AccountOut.model_validate(account),
    )


@router.post("/auth/otp/request", status_code=status.HTTP_204_NO_CONTENT)
def otp_request(
    body: OtpRequestIn,
    request: Request,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> Response:
    """Send an OTP to `phone`. Always 204 for a valid number; 429 when rate-limited."""
    try:
        request_code(db, redis_client, body.phone, _client_ip(request))
    except InvalidPhone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid phone number"
        ) from exc
    except OtpRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/otp/peek")
def otp_peek(
    phone: str = Query(...),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> dict[str, str]:
    """E2E test hook: return the pending OTP code. DOUBLE-GATED — 404 unless the
    console SMS driver is active AND DEBUG is on (i.e. never in prod)."""
    if not (settings.DEBUG and settings.SMS_PROVIDER == "console"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        normalized = normalize_phone(phone)
    except InvalidPhone as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    code = redis_client.get(peek_key(normalized))
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"code": code}


@router.post("/auth/otp/verify", response_model=PortalTokenResponse)
def otp_verify(
    body: OtpVerifyIn,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> PortalTokenResponse:
    """Verify the OTP; issue a portal access token + set the portal_session cookie."""
    try:
        account = verify_code(db, redis_client, body.phone, body.code)
    except InvalidPhone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid phone number"
        ) from exc
    except OtpLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts"
        ) from exc
    except OtpInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code"
        ) from exc

    if account.status != AccountStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")

    db.commit()  # the OTP verify endpoint owns the account-upsert transaction
    set_portal_session_cookie(response, account.id)
    return _token_response(account)


@router.post("/auth/refresh", response_model=PortalTokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    portal_session: str | None = Cookie(default=None, alias=_PORTAL_COOKIE),
) -> PortalTokenResponse:
    """Rotate the portal_session cookie and mint a fresh access token."""
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

    set_portal_session_cookie(response, account.id)  # rotation: new jti ⇒ new cookie
    return _token_response(account)


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    """Clear the portal_session cookie (client discards the in-memory access token)."""
    clear_portal_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=AccountOut)
def get_me(account: UserAccount = Depends(get_current_account)) -> AccountOut:
    return AccountOut.model_validate(account)


@router.patch("/me", response_model=AccountOut)
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
