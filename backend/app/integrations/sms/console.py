"""Console SMS driver (dev/CI) — logs the message instead of sending it.

This is the ONLY place an OTP code is ever written to a log, and only under the
console driver (SMS_PROVIDER=console, i.e. never in prod). `otp_service` itself
never logs the code. The demo/e2e flow reads the code from the worker log line
this emits.
"""

from __future__ import annotations

import logging

from app.integrations.sms.base import SmsSendResult

logger = logging.getLogger(__name__)


class ConsoleSmsProvider:
    """Dev/CI provider: prints the SMS to the worker log, always succeeds."""

    provider_name = "console"

    async def send(self, phone: str, text: str) -> SmsSendResult:
        # Deliberate dev-only visibility of the code; gated by SMS_PROVIDER=console.
        logger.info("sms.console.send phone=%s text=%r", phone, text)
        return SmsSendResult(ok=True, provider_msg_id=None, error=None)
