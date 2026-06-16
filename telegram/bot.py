"""Aiogram 3 Bot/Dispatcher singletons and helpers.

Provides:
- bot: aiogram.Bot singleton (lazy-initialized — not constructed at module import time
  so that importing telegram.bot under pytest does not open a network socket).
- dp: aiogram.Dispatcher singleton (wired with start_router).
- setup_webhook(): registers the webhook URL + chat menu button with Telegram.
  No-ops when PUBLIC_WEBAPP_URL is empty so dev/test environments never call Telegram.
- load_template(lang, name): reads telegram/templates/{lang}/{name}.txt,
  falls back to 'ru' if the lang directory is missing.
- web_app_keyboard(lang): returns an InlineKeyboardMarkup with a single WebAppInfo
  button pointing to settings.PUBLIC_WEBAPP_URL.

Dev-spec §4.1: webhook-only, no long-polling, runs in the api container.
D-06: persistent Web App menu button set via BotCommandScopeDefault.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Directory containing the template files (telegram/templates/)
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# ── Localized labels ──────────────────────────────────────────────────────────
_WEB_APP_BUTTON_LABELS: dict[str, str] = {
    "ru": "Открыть приложение",
    "uz": "Ilovani ochish",
}


# ── Template helper ───────────────────────────────────────────────────────────

def load_template(lang: str, name: str) -> str:
    """Read and return the content of telegram/templates/{lang}/{name}.txt.

    Falls back to 'ru' if the requested language directory does not exist
    (e.g. when a new language is added to settings but templates are not yet
    translated).

    Args:
        lang: Language code ('ru' or 'uz').
        name: Template file name without extension (e.g. 'start', 'status_change').

    Returns:
        The template content as a string.

    Raises:
        FileNotFoundError: If neither the requested language nor the 'ru' fallback
            template exists.
    """
    path = _TEMPLATES_DIR / lang / f"{name}.txt"
    if not path.exists():
        # Fallback to Russian
        path = _TEMPLATES_DIR / "ru" / f"{name}.txt"
    return path.read_text(encoding="utf-8")


# ── Keyboard helper ───────────────────────────────────────────────────────────

def web_app_keyboard(lang: str) -> "InlineKeyboardMarkup":
    """Return an inline keyboard with a single WebApp launch button.

    The button label is localized (RU: "Открыть приложение", UZ: "Ilovani ochish").
    Points to settings.PUBLIC_WEBAPP_URL.

    Args:
        lang: Language code — determines the button label.

    Returns:
        aiogram InlineKeyboardMarkup with one WebAppInfo button.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo  # noqa: PLC0415

    label = _WEB_APP_BUTTON_LABELS.get(lang, _WEB_APP_BUTTON_LABELS["ru"])
    button = InlineKeyboardButton(
        text=label,
        web_app=WebAppInfo(url=settings.PUBLIC_WEBAPP_URL or "https://example.com"),
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


# ── Webhook setup ─────────────────────────────────────────────────────────────

async def setup_webhook() -> None:
    """Register the webhook URL and persistent Web App menu button with Telegram.

    Called from the FastAPI lifespan hook in backend/app/main.py only when
    settings.PUBLIC_WEBAPP_URL is non-empty. This guard ensures that dev/test
    environments with no PUBLIC_WEBAPP_URL set never attempt to call Telegram.

    D-06: sets the chat menu button to a WebApp button for all users so clients
    see the persistent "Open App" entry at the bottom of the chat.
    """
    # Guard: no-op when PUBLIC_WEBAPP_URL is not configured (dev/CI)
    if not settings.PUBLIC_WEBAPP_URL:
        logger.debug("setup_webhook.skipped: PUBLIC_WEBAPP_URL is empty")
        return

    from aiogram.types import BotCommandScopeDefault, MenuButtonWebApp, WebAppInfo  # noqa: PLC0415

    webhook_url = (
        f"{settings.PUBLIC_WEBAPP_URL}/api/v1/telegram/webhook/{settings.WEBHOOK_SECRET}"
    )

    logger.info("setup_webhook.start", extra={"webhook_url": webhook_url})

    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET,
        drop_pending_updates=True,
    )

    # D-06: persistent Web App button in the chat menu
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Открыть приложение",
            web_app=WebAppInfo(url=settings.PUBLIC_WEBAPP_URL),
        )
    )

    logger.info("setup_webhook.done")


# ── Bot / Dispatcher singletons ───────────────────────────────────────────────
# Constructed lazily at module import time — aiogram.Bot does not open a
# network socket merely by being instantiated, so this is import-safe.
# The token is read from settings which reads from the environment.

def _create_bot() -> "Bot":
    """Construct and return the aiogram Bot singleton."""
    from aiogram import Bot as _Bot  # noqa: PLC0415
    from aiogram.client.default import DefaultBotProperties  # noqa: PLC0415
    from aiogram.enums import ParseMode  # noqa: PLC0415

    return _Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _create_dispatcher() -> "Dispatcher":
    """Construct the aiogram Dispatcher and wire up all routers."""
    from aiogram import Dispatcher as _Dispatcher  # noqa: PLC0415
    from telegram.handlers.start import start_router  # noqa: PLC0415

    _dp = _Dispatcher()
    _dp.include_router(start_router)
    return _dp


# Module-level singletons (constructed at import time; import-safe since
# aiogram Bot/Dispatcher do not open network sockets on construction).
bot: "Bot" = _create_bot()  # type: ignore[assignment]
dp: "Dispatcher" = _create_dispatcher()  # type: ignore[assignment]
