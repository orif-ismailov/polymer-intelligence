"""
telegram_channel adapter package.

Importing this package self-registers the TelegramChannelAdapter
(telegram_channel) into the global adapter registry.

Usage:
    import app.ingest.telegram_channel  # registers TelegramChannelAdapter
"""

from app.ingest.telegram_channel import adapter  # noqa: F401

__all__ = ["adapter"]
