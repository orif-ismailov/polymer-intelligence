"""SMS provider port (R1 W3 — T3.1).

The `SmsProvider` Protocol is the seam between OTP auth and whatever actually
delivers the message: the `console` driver (dev/CI — logs instead of sending) or
`eskiz` (real SMS in prod). `get_sms_provider()` (in this package's __init__)
picks one from `settings.SMS_PROVIDER`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SmsSendResult:
    """Outcome of a single SMS send attempt.

    `ok` drives the `sms_send_log.status` value; `provider_msg_id` is the
    provider's message handle (for cost reconciliation / support); `error` holds
    a short reason string when `ok` is False. The OTP code is NEVER stored here.
    """

    ok: bool
    provider_msg_id: str | None = None
    error: str | None = None


@runtime_checkable
class SmsProvider(Protocol):
    """A pluggable SMS delivery backend."""

    provider_name: str

    async def send(self, phone: str, text: str) -> SmsSendResult:
        """Deliver `text` to `phone` (E.164). Must not raise — return a result."""
        ...
