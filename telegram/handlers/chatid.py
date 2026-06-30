"""
/chatid handler — replies with the current chat's numeric id and type.

Use it to find a group's id for REQUEST_NOTIFY_CHAT_ID: add the bot to the group,
send /chatid (or /chatid@YourBot if group privacy mode is on), and copy the id
(e.g. -1001234567890).
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

chatid_router = Router()


@chatid_router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    """Reply with the chat id + type (works in private chats, groups and channels)."""
    chat = message.chat
    lines = [
        f"<b>Chat ID:</b> <code>{chat.id}</code>",
        f"<b>Type:</b> {chat.type}",
    ]
    if chat.title:
        lines.append(f"<b>Title:</b> {chat.title}")
    await message.reply("\n".join(lines))
    logger.info("cmd_chatid", extra={"chat_id": chat.id, "chat_type": chat.type})
