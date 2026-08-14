"""Aiogram /start command handler.

D-06: greets the client in RU or UZ (derived from message.from_user.language_code),
shows a Web App inline launch button, and creates/upserts the clients row via
client_service.get_or_create_client().

Handler pattern:
- NO business logic in the handler — delegates entirely to client_service.
- Opens its own Session(engine) to avoid dependency on FastAPI's get_db lifecycle.
- Commits after the service call (the handler owns the transaction, per
  DEC-dep-owns-commit pattern extended to bot handlers).
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.orm import Session

from app.core.db import engine

logger = logging.getLogger(__name__)

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """/start handler: upsert client, send localized greeting + Web App button.

    Language selection:
    - Reads message.from_user.language_code (e.g. 'ru', 'uz', 'en').
    - Normalizes to 'ru' or 'uz'; all other codes default to 'ru'.

    Upsert:
    - Calls client_service.get_or_create_client() with telegram_user_id,
      normalized language, and full_name as contact_name.
    - Commits the session after the service call.

    Response:
    - Renders telegram/templates/{lang}/start.txt via load_template().
    - Attaches web_app_keyboard(lang) with the localized Web App button.
    """
    from app.domains.requests.clients import get_or_create_client  # noqa: PLC0415
    from telegram.bot import load_template, web_app_keyboard  # noqa: PLC0415

    if message.from_user is None:
        logger.warning("cmd_start: received message with no from_user")
        return

    # Normalize language_code to a supported language; anything else → default (ru)
    from app.core.languages import normalize_language  # noqa: PLC0415

    lang = normalize_language(message.from_user.language_code)

    telegram_user_id: int = message.from_user.id
    contact_name: str | None = message.from_user.full_name or None

    logger.info(
        "cmd_start.start",
        extra={"telegram_user_id": telegram_user_id, "lang": lang},
    )

    # Upsert clients row — handler owns the session + commit
    with Session(engine) as db:
        get_or_create_client(
            db=db,
            telegram_user_id=telegram_user_id,
            language=lang,
            contact_name=contact_name,
        )
        db.commit()

    # Load localized greeting template and reply with Web App button
    text = load_template(lang, "start")
    await message.answer(text, reply_markup=web_app_keyboard(lang))

    logger.info(
        "cmd_start.done",
        extra={"telegram_user_id": telegram_user_id, "lang": lang},
    )
