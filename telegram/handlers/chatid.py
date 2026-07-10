"""
/chatid handler — replies with the current chat's numeric id and type.

Use it to find a group's id for REQUEST_NOTIFY_CHAT_ID: add the bot to the group,
send /chatid (or /chatid@YourBot if group privacy mode is on), and copy the id
(e.g. -1001234567890).

In a forum group, send /chatid INSIDE a topic and it also reports that topic's
Thread ID — copy it into NOTIFY_TOPIC_BUYERS / NOTIFY_TOPIC_SELLERS to route
notifications into that topic.
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
    # In a forum, a message sent inside a topic carries its thread id. The General
    # topic reports no thread id (is_topic_message is falsy there).
    thread_id = message.message_thread_id if message.is_topic_message else None
    if thread_id is not None:
        lines.append(f"<b>Topic (Thread) ID:</b> <code>{thread_id}</code>")
    await message.reply("\n".join(lines))
    logger.info(
        "cmd_chatid",
        extra={"chat_id": chat.id, "chat_type": chat.type, "thread_id": thread_id},
    )
