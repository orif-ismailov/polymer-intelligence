"""
/webapp/auth — browser authentication via the Telegram Login Widget.

The Mini App authenticates with initData (X-Telegram-Init-Data, see market/me/…).
This router adds the BROWSER path: visitors who open the webapp outside Telegram
sign in with the Telegram Login Widget. On success we issue an httpOnly
``client_session`` cookie (see auth_service.set_client_session_cookie) so
get_current_client accepts them on every subsequent /webapp/* call.

Routes (ALL public — no get_current_client dependency):
- GET  /webapp/auth/config   → the bot @handle + login TTL for the widget script.
- POST /webapp/auth/telegram → verify the widget payload, upsert Client, set cookie.
- POST /webapp/auth/logout   → clear the cookie.

Security: the widget HMAC is verified with a DIFFERENT algorithm from initData
(secret = SHA256(BOT_TOKEN)); see client_service.verify_login_widget. Every failure
returns the same generic 401 (T-03-03).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.services.auth_service import (
    clear_client_session_cookie,
    set_client_session_cookie,
)

router = APIRouter(prefix="/webapp/auth", tags=["webapp-auth"])


@router.get("/config", summary="Public webapp auth config (bot handle for the Login Widget)")
def auth_config() -> dict[str, object]:
    """GET /webapp/auth/config — runtime config the static bundle needs to render the
    Telegram Login Widget. `bot_username` empty ⇒ the frontend hides browser login."""
    return {
        "bot_username": settings.BOT_USERNAME,
        "login_ttl": settings.TELEGRAM_INIT_DATA_TTL_SECONDS,
    }


@router.post("/telegram", summary="Authenticate a browser visitor via the Telegram Login Widget")
def login_telegram(
    response: Response,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """POST /webapp/auth/telegram — verify the Login Widget callback and start a session.

    The body is the exact object Telegram's widget produced (id, first_name, auth_date,
    hash, …). It is passed through verbatim to verify_login_widget so the data-check
    string matches the fields Telegram actually signed.

    Raises:
        HTTPException 401: on any verification failure (generic — T-03-03).
        HTTPException 404: if browser login is not configured (no BOT_USERNAME).
    """
    if not settings.BOT_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Browser login is not enabled",
        )

    from app.services.client_service import (  # noqa: PLC0415
        InvalidInitData,
        get_or_create_client,
        verify_login_widget,
    )

    try:
        verified = verify_login_widget({k: str(v) for k, v in payload.items()})
    except (InvalidInitData, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        ) from None

    telegram_user_id = int(verified["id"])  # coerced to int by verify_login_widget
    first_name = verified.get("first_name")
    contact_name = str(first_name) if first_name else None

    get_or_create_client(
        db=db,
        telegram_user_id=telegram_user_id,
        language=str(verified.get("language_code", "ru")),
        contact_name=contact_name,
    )
    db.commit()  # the endpoint owns the upsert transaction

    set_client_session_cookie(response, telegram_user_id)
    return {"ok": True}


@router.post("/logout", summary="Clear the browser client-session cookie")
def logout(response: Response) -> dict[str, bool]:
    """POST /webapp/auth/logout — clear the client_session cookie (browser sign-out)."""
    clear_client_session_cookie(response)
    return {"ok": True}
