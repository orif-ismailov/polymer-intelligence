"""Didox partner-API gateway (R6 / P7.a).

Didox (ООО «DIDOX TECH», ИНН 310529901) is Uzbekistan's largest private EDI
operator. Stage 1 uses one endpoint of it — `GET /v1/utils/info/{TinOrPinfl}`,
the tax registry's own record of a company — to fill the registration form and
to feed the P7.c verification checks. The rest of the ported surface (documents,
DSVS, catalogs) lands with the signing rails.

Shape is `integrations/eimzo/client.py` verbatim: injectable transport, a circuit
breaker, one `integration_call_log` row per call on an isolated session, and the
split that matters —

  * **5xx / transport / open breaker → `ProviderUnavailable`** (an outage; the
    caller degrades, nothing is decided about the company);
  * **4xx → `DidoxError`** (our request was wrong; it does NOT trip the breaker),
    except **401/403, which are ALSO an outage**: production refuses this
    endpoint without a `user-key` (`Token expired` with none, `Invalid user key`
    with a stale one), and that is a statement about our configuration, never
    about the company being looked up.

The auth model is two independent tokens, both documented in the skill
(`~/.claude/skills/didox`):

    Partner-Authorization: <PARTNER_TOKEN>   # integrator identity — server-side SECRET
    user-key: <USER_TOKEN>                   # the acting user/company — UUID, TTL 360 min

`Partner-Authorization` rides on **every** request including auth. The user-key
cannot be minted server-side for an arbitrary company (it needs that company's
E-IMZO key), which is why `auth.py` mints one for OUR OWN service account and
why its absence degrades rather than fails.

One behaviour no reading of the docs would have revealed, recorded live against
`testapi3` on 2026-08-15 and pinned by the tests: **"no such company" is a 200
with an envelope full of nulls**, not a 404. `DidoxCompanyInfo.from_payload`
returns `None` for it — an empty DTO would put a blank legal name in a form and
an "unknown" registry status on a verification check.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.integrations.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_PROVIDER = "didox"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)

TEST_BASE_URL = "https://testapi3.didox.uz"
PROD_BASE_URL = "https://api-partners.didox.uz"


class ProviderUnavailable(Exception):
    """Didox is unreachable/slow/5xx, the breaker is open, or our auth is unusable."""


class DidoxError(Exception):
    """Didox answered 4xx: our request was wrong.

    `trace_id` is the `x-trace-id` echoed back in `errorDetails.id` — quote it to
    Didox support. `description` is their own "what to do about it" text, present
    only for errors they have an explanation for.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        trace_id: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(f"didox {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.trace_id = trace_id
        self.description = description


def _text(value: Any) -> str | None:  # noqa: ANN401 — untrusted provider JSON
    """Trim to None. Didox pads several fields with trailing spaces, and an
    address with a ragged tail is visible the moment it lands in a form field."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _int(value: Any) -> int | None:  # noqa: ANN401
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _ru_date(value: Any) -> datetime.date | None:  # noqa: ANN401
    """Parse Didox's `dd.mm.yyyy`, tolerating ISO and anything else.

    Every date we store is a real `date`; a string here would reach
    `companies.registration_date` as a type error at insert time, i.e. at the
    worst possible moment.
    """
    text = _text(value)
    if text is None:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    logger.warning("didox.bad_date", extra={"value": text})
    return None


@dataclass(frozen=True)
class DidoxCompanyInfo:
    """The registry record behind `/v1/utils/info/{tin}`.

    Richer than `gov_registry.CompanySnapshot` on purpose: the snapshot is what
    the verification checks judge, while this also carries what a registration
    form wants to prefill (short name, legal form, bank requisites, VAT code).
    `registry.py` narrows it to the protocol DTOs.
    """

    tin: str
    name: str | None = None
    short_name: str | None = None
    legal_form: str | None = None
    address: str | None = None
    oked: str | None = None
    registered_at: datetime.date | None = None
    status_code: int | None = None
    status_name: str | None = None
    director: str | None = None
    director_pinfl: str | None = None
    director_tin: str | None = None
    accountant: str | None = None
    bank_mfo: str | None = None
    bank_account: str | None = None
    vat_reg_code: str | None = None
    vat_reg_status: int | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> DidoxCompanyInfo | None:  # noqa: ANN401
        """Parse a lookup response, or `None` when the registry has no record.

        Didox signals "not found" with HTTP 200 and an envelope whose every
        field is null or "" — so absence is detected here, once, rather than by
        each caller noticing an empty name.
        """
        if not isinstance(payload, dict):
            return None
        tin = _text(payload.get("tin"))
        name = _text(payload.get("name")) or _text(payload.get("fullName"))
        if tin is None and name is None:
            return None
        return cls(
            tin=tin or "",
            name=name,
            short_name=_text(payload.get("shortName")) or _text(payload.get("shortname")),
            legal_form=_text(payload.get("na1Name")),
            address=_text(payload.get("address")),
            oked=_text(payload.get("oked")),
            registered_at=_ru_date(payload.get("regDate")),
            status_code=_int(payload.get("statusCode")),
            status_name=_text(payload.get("statusName")),
            director=_text(payload.get("director")),
            director_pinfl=_text(payload.get("directorPinfl")),
            director_tin=_text(payload.get("directorTin")),
            accountant=_text(payload.get("accountant")),
            bank_mfo=_text(payload.get("mfo")) or _text(payload.get("bankCode")),
            bank_account=_text(payload.get("account")) or _text(payload.get("bankAccount")),
            vat_reg_code=_text(payload.get("VATRegCode")),
            vat_reg_status=_int(payload.get("VATRegStatus")),
        )


class DidoxClient:
    """Thin, testable client for the Didox partner API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        partner_token: str | None = None,
        user_key: str | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
        breaker: CircuitBreaker | None = None,
        session_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if base_url is None or partner_token is None:
            from app.core.config import settings  # noqa: PLC0415 — lazy: import-safe module

            base_url = base_url if base_url is not None else settings.DIDOX_BASE_URL
            partner_token = (
                partner_token if partner_token is not None else settings.DIDOX_PARTNER_TOKEN
            )
        self._base_url = base_url.rstrip("/")
        self._partner_token = partner_token
        self._user_key = user_key
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=_TIMEOUT))
        self._breaker = breaker or CircuitBreaker()
        self._session_factory = session_factory
        self._clock = clock

    # ── public surface (Stage 1) ──────────────────────────────────────────────

    def info_by_tin(self, tin: str, *, user_key: str | None = None) -> DidoxCompanyInfo | None:
        """Registry record for an INN/ПИНФЛ, or `None` when there is no record."""
        body = self._request("GET", f"/v1/utils/info/{tin}", "info_by_tin", user_key=user_key)
        return DidoxCompanyInfo.from_payload(body)

    def banks(self, *, user_key: str | None = None) -> Any:  # noqa: ANN401
        """МФО classifier. Needs no user-key on either contour."""
        return self._request("GET", "/v1/banks/all", "banks", user_key=user_key)

    def measures(self, *, user_key: str | None = None) -> Any:  # noqa: ANN401
        """Units of measure (`packagecode`/`packagename` for document lines)."""
        return self._request("GET", "/v1/measures/all", "measures", user_key=user_key)

    def auth_by_password(self, tax_id: str, password: str, locale: str = "ru") -> str:
        """Mint a `user-key` by password → the token (a UUID, TTL 360 minutes).

        **Never call this in a loop.** The lockout ladder is 3 wrong/min → 10 min,
        10 → 24 h, 25 → PERMANENT (`reference/03-login.md`); `auth.py` enforces
        one attempt per cache miss.
        """
        body = self._request(
            "POST",
            f"/v1/auth/{tax_id}/password/{locale}",
            "auth_by_password",
            json_body={"password": password},
        )
        token = (body or {}).get("token") if isinstance(body, dict) else None
        if not token:
            raise ProviderUnavailable("didox: auth response carried no token")
        return str(token)

    # ── plumbing ──────────────────────────────────────────────────────────────

    def _headers(self, user_key: str | None) -> dict[str, str]:
        headers = {
            "Partner-Authorization": self._partner_token,
            "Accept-Language": "ru",
        }
        key = user_key or self._user_key
        if key:
            # Only when we actually have one — an empty header reads as a bad key.
            headers["user-key"] = key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        user_key: str | None = None,
        json_body: Any = None,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        if self._breaker.is_open():
            self._log_call(operation, ok=False, status_code=None, latency_ms=None, error="breaker_open")
            raise ProviderUnavailable("didox: circuit open")

        started = self._clock()
        try:
            with self._client_factory() as client:
                resp = client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=self._headers(user_key),
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            self._log_call(
                operation,
                ok=False,
                status_code=None,
                latency_ms=self._elapsed_ms(started),
                error=type(exc).__name__,
            )
            logger.warning("didox.transport_error", extra={"error": str(exc), "op": operation})
            raise ProviderUnavailable(f"didox: {type(exc).__name__}") from exc

        latency_ms = self._elapsed_ms(started)
        if resp.status_code >= 500:
            self._breaker.record_failure()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_5xx")
            raise ProviderUnavailable(f"didox: {resp.status_code}")

        if resp.status_code in (401, 403):
            # Auth, not content. Prod refuses the lookup without a user-key and
            # says "Token expired"; treating that as a domain answer would let a
            # misconfiguration masquerade as a fact about a company. It is not
            # the provider failing either, so the breaker stays closed.
            self._breaker.record_success()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_auth")
            raise ProviderUnavailable(f"didox: {resp.status_code} {self._message(resp)}")

        if resp.status_code >= 400:
            self._breaker.record_success()
            self._log_call(operation, ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="didox_4xx")
            raise self._to_error(resp)

        self._breaker.record_success()
        self._log_call(operation, ok=True, status_code=resp.status_code, latency_ms=latency_ms, error=None)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning("didox.bad_json", extra={"op": operation})
            return None

    @staticmethod
    def _message(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
        except ValueError:
            return resp.text.strip()[:200] or resp.reason_phrase
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str):
                return message
        return resp.reason_phrase

    def _to_error(self, resp: httpx.Response) -> DidoxError:
        """Normalize Didox's several error envelopes into one exception."""
        message = self._message(resp)
        trace_id: str | None = None
        description: str | None = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            details = payload.get("errorDetails")
            if isinstance(details, dict) and details:
                trace_id = _text(details.get("id"))
                description = _text(details.get("description"))
                message = _text(details.get("message")) or message
            data = payload.get("data")
            if isinstance(data, dict) and _text(data.get("message")):
                message = str(data["message"])
        return DidoxError(resp.status_code, message, trace_id=trace_id, description=description)

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))

    def _log_call(
        self,
        operation: str,
        *,
        ok: bool,
        status_code: int | None,
        latency_ms: int | None,
        error: str | None,
    ) -> None:
        """Best-effort `integration_call_log` row on an isolated session (never raises).

        Metadata only — never a request or response body. A lookup response
        carries a director's ПИНФЛ and a bank account.
        """
        if self._session_factory is None:
            return
        try:
            from app.models.integration import IntegrationCallLog  # noqa: PLC0415

            with self._session_factory() as db:
                db.add(
                    IntegrationCallLog(
                        provider=_PROVIDER,
                        operation=operation,
                        ok=ok,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001 — the call log must never break a lookup
            logger.warning("didox.call_log.failed", extra={"error": str(exc)})


# ── Process singleton ──────────────────────────────────────────────────────────

_client: DidoxClient | None = None


def get_didox_client() -> DidoxClient:
    """The process-wide client (call-logs to the app DB via SessionLocal)."""
    global _client
    if _client is None:
        from app.core.db import SessionLocal  # noqa: PLC0415

        _client = DidoxClient(session_factory=SessionLocal)
    return _client


def is_configured() -> bool:
    """True when a partner token exists. Without one every call is a 401, so the
    caller should degrade before spending a request finding that out."""
    from app.core.config import settings  # noqa: PLC0415

    return bool(settings.DIDOX_PARTNER_TOKEN)
