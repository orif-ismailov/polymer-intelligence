"""
Telethon client factory.

Builds a TelegramClient using the StringSession + API credentials from
environment (via settings).

One-time session string generation (developer setup, NOT production):
----------------------------------------------------------------------
Run this ONCE interactively on your local machine to generate the session string.
The string must be stored in .env as TG_SESSION_STRING and NEVER committed to git.

    python - << 'EOF'
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    import os

    api_id   = int(input("TG_API_ID: "))
    api_hash = input("TG_API_HASH: ")

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("Your session string (copy to .env TG_SESSION_STRING):")
        print(client.session.save())
    EOF

Security (T-05-05):
  - TG_SESSION_STRING is read from settings, NEVER a source literal.
  - The .env file is NOT committed (it is in .gitignore).
  - deploy/.env.example marks TG_SESSION_STRING as [SECRET].
  - The grep gate in plan acceptance confirms no hardcoded session string.

Customer handoff note:
  The customer must provide TG_API_ID and TG_API_HASH from my.telegram.org,
  and generate TG_SESSION_STRING using the above one-time login flow.
  Without these three values this module raises a clear startup error.
"""

from __future__ import annotations

import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

# Import settings lazily to allow the module to be imported in tests without
# a live environment (the build_client() function does the validation).
def build_client() -> TelegramClient:
    """Build and return a Telethon TelegramClient using StringSession credentials.

    Reads TG_API_ID, TG_API_HASH, and TG_SESSION_STRING from settings.
    Raises RuntimeError with a clear message if TG_SESSION_STRING is empty,
    pointing at the customer-input handoff documented above.

    Returns:
        TelegramClient — NOT yet connected; call ``async with client:`` or
        ``await client.connect()`` before use.
    """
    # Import here (not at module top) so tests that don't call build_client()
    # can import userbot.session without a live Settings environment.
    from app.core.config import settings  # noqa: PLC0415

    if not settings.TG_SESSION_STRING:
        print(
            "FATAL: TG_SESSION_STRING is not set.\n"
            "The Telegram userbot requires a session string generated via the\n"
            "one-time interactive login described in userbot/session.py.\n"
            "Steps:\n"
            "  1. Obtain TG_API_ID and TG_API_HASH from https://my.telegram.org\n"
            "  2. Run the interactive login script in userbot/session.py\n"
            "  3. Copy the printed session string to .env as TG_SESSION_STRING\n"
            "This is a customer-side handoff item (see plan 05-02 user_setup).",
            file=sys.stderr,
        )
        raise RuntimeError(
            "TG_SESSION_STRING is empty — userbot cannot start without a valid session. "
            "See userbot/session.py for the one-time generation procedure."
        )

    return TelegramClient(
        StringSession(settings.TG_SESSION_STRING),
        int(settings.TG_API_ID),
        settings.TG_API_HASH,
    )
