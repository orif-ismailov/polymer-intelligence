"""Eskiz.uz SMS provider (prod) — R1 W3 T3.1.

Auth: POST /api/auth/login (email/password → JWT), cached on the instance and
refreshed once on a 401. Send: POST /api/message/sms/send. Network/auth failures
degrade to `SmsSendResult(ok=False, ...)` — the task logs and records the failure
rather than raising (a dead provider must not break the OTP path).

The instance is a process singleton (see `get_sms_provider`) so the JWT is reused
across sends. `client_factory` is injectable for tests (httpx.MockTransport).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from app.core.config import settings
from app.integrations.sms.base import SmsSendResult

logger = logging.getLogger(__name__)

_AUTH_URL = "https://notify.eskiz.uz/api/auth/login"
_SEND_URL = "https://notify.eskiz.uz/api/message/sms/send"
# Eskiz's default originator; production accounts register their own approved sender.
_SENDER = "4546"


class EskizSmsProvider:
    """Sends SMS through Eskiz.uz with a cached, self-refreshing JWT."""

    provider_name = "eskiz"

    def __init__(self, client_factory: Callable[[], httpx.AsyncClient] | None = None) -> None:
        self._token: str | None = None
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=10.0))

    async def _login(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            _AUTH_URL,
            data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
        )
        resp.raise_for_status()
        token = str(resp.json()["data"]["token"])
        self._token = token
        return token

    async def send(self, phone: str, text: str) -> SmsSendResult:
        digits = "".join(ch for ch in phone if ch.isdigit())
        try:
            async with self._client_factory() as client:
                if not self._token:
                    await self._login(client)
                # One retry: a stale cached token → 401 → re-login → resend once.
                for attempt in range(2):
                    resp = await client.post(
                        _SEND_URL,
                        data={"mobile_phone": digits, "message": text, "from": _SENDER},
                        headers={"Authorization": f"Bearer {self._token}"},
                    )
                    if resp.status_code == 401 and attempt == 0:
                        await self._login(client)
                        continue
                    resp.raise_for_status()
                    body = resp.json()
                    msg_id = body.get("id") or body.get("message_id")
                    return SmsSendResult(
                        ok=True,
                        provider_msg_id=str(msg_id) if msg_id is not None else None,
                        error=None,
                    )
        except Exception as exc:  # noqa: BLE001 — degrade, never raise into the task
            logger.warning("sms.eskiz.error", extra={"error": str(exc)})
            return SmsSendResult(ok=False, provider_msg_id=None, error=str(exc))

        return SmsSendResult(ok=False, provider_msg_id=None, error="eskiz: unreachable")
