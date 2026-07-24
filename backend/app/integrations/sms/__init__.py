"""SMS integration package + provider factory (R1 W3 — T3.1).

`get_sms_provider()` returns the provider selected by `settings.SMS_PROVIDER`
(`console` default, `eskiz` in prod). The Eskiz instance is a process singleton so
its JWT is cached across sends; the console driver is stateless.
"""

from __future__ import annotations

from app.core.config import settings
from app.integrations.sms.base import SmsProvider, SmsSendResult
from app.integrations.sms.console import ConsoleSmsProvider
from app.integrations.sms.eskiz import EskizSmsProvider

__all__ = ["SmsProvider", "SmsSendResult", "get_sms_provider"]

_console = ConsoleSmsProvider()
_eskiz: EskizSmsProvider | None = None


def get_sms_provider() -> SmsProvider:
    """Return the configured SMS provider (reads `settings.SMS_PROVIDER` per call)."""
    if settings.SMS_PROVIDER == "eskiz":
        global _eskiz
        if _eskiz is None:
            _eskiz = EskizSmsProvider()
        return _eskiz
    return _console
