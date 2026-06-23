"""Telegram bot package — aiogram 3 webhook-based client bot.

Provides the Bot/Dispatcher singletons, the /start handler, and helper
utilities used by both the FastAPI webhook router (backend/app/api/telegram_webhook.py)
and the Celery notify task (backend/app/tasks/notify.py).

Dev-spec §4.1: the bot runs as a webhook endpoint inside the api container —
NOT a separate container, NOT long-polling.
"""
