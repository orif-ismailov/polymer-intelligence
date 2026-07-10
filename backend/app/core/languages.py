"""Supported UI languages — single source of truth.

The clients.language column is VARCHAR(2), so adding a language needs no DB
migration. Every place that validates or normalizes a language code (the bot
/start handler, client_service, and the webapp PATCH /me validator) imports from
here so the supported set is defined once.

Adding a language: append its 2-letter code to SUPPORTED_LANGUAGES, add the bot
templates under telegram/templates/<code>/, the webapp locale JSON, and the
dashboard messages/<code>.json.
"""

from __future__ import annotations

# ISO 639-1 codes the product is localized into
# (Russian, English, Turkish, Uzbek, Persian/Farsi, Chinese).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("ru", "en", "tr", "uz", "fa", "zh")

# Fallback when a code is missing/unsupported (e.g. a Telegram language_code we
# don't localize into). Russian is the operator/primary market default.
DEFAULT_LANGUAGE: str = "ru"


def normalize_language(code: str | None) -> str:
    """Return code if it is a supported language, else DEFAULT_LANGUAGE."""
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
