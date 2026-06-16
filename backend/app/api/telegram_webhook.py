"""
POST /telegram/webhook/{secret} — Telegram bot webhook endpoint.

Security (T-03-11: Spoofing mitigation):
  Both the path secret AND the X-Telegram-Bot-Api-Secret-Token header must match
  settings.WEBHOOK_SECRET via hmac.compare_digest (constant-time comparison).
  A mismatch on either check raises HTTP 403.

Dev-spec §4.1: the bot runs as a webhook endpoint inside the api container.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post(
    "/webhook/{secret}",
    summary="Receive Telegram update via webhook",
    description=(
        "Receives a Telegram Update JSON payload. "
        "Both the URL path {secret} and the X-Telegram-Bot-Api-Secret-Token header "
        "must match settings.WEBHOOK_SECRET (constant-time comparison, T-03-11). "
        "Mismatched secret → 403."
    ),
)
async def telegram_webhook(
    secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict[str, bool]:
    """Process incoming Telegram update.

    Security checks (T-03-11: defense in depth against forged webhook updates):
    1. Path secret compared to WEBHOOK_SECRET via hmac.compare_digest.
    2. X-Telegram-Bot-Api-Secret-Token header compared to WEBHOOK_SECRET via
       hmac.compare_digest.
    Both checks must pass; either failure returns HTTP 403.

    Args:
        secret: URL path segment carrying the webhook secret.
        request: The raw FastAPI Request (used to read the JSON body).
        x_telegram_bot_api_secret_token: Telegram's secret_token header.

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException 403: Path secret or header secret mismatches WEBHOOK_SECRET.
    """
    expected = settings.WEBHOOK_SECRET

    # T-03-11: constant-time comparison to prevent timing oracle attacks.
    # Both path secret AND header must match.
    path_ok = hmac.compare_digest(secret, expected)

    header_ok = (
        x_telegram_bot_api_secret_token is not None
        and hmac.compare_digest(x_telegram_bot_api_secret_token, expected)
    )

    if not (path_ok and header_ok):
        logger.warning(
            "telegram_webhook.rejected",
            extra={
                "path_ok": path_ok,
                "header_ok": header_ok,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    # Parse the JSON body into an aiogram Update and feed it to the Dispatcher.
    # Lazy imports keep this module import-safe (no network sockets at import time).
    from aiogram.types import Update  # noqa: PLC0415

    from telegram.bot import bot, dp  # noqa: PLC0415

    body = await request.json()

    logger.info(
        "telegram_webhook.received",
        extra={"update_id": body.get("update_id")},
    )

    update = Update.model_validate(body)
    await dp.feed_update(bot, update)

    logger.info("telegram_webhook.done", extra={"update_id": body.get("update_id")})
    return {"ok": True}
