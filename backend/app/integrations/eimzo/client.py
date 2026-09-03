"""E-IMZO gateway adapter (R3 TA1.2 — ARCHITECTURE §9.6, §12).

`verify_pkcs7(pkcs7_b64, challenge)` delegates PKCS#7 verification to the UNICON
**e-imzo-server** sidecar (national O'zDSt crypto — stock libs cannot verify it)
and returns a normalized `EimzoVerifyResult`. It NEVER raises a raw HTTP error into
domain code:

  * a valid signature → `EimzoVerifyResult(ok=True, signer=…, cert_valid_*, revoked)`;
  * an *invalid* signature / challenge mismatch → `ok=False` with `error` (a domain
    result, not an outage — does not trip the breaker);
  * the sidecar being unreachable / slow / 5xx, or the breaker being open →
    `ProviderUnavailable` (mapped to a 503 upstream; the manual path stays open).

Timeouts: 5 s connect / 15 s read. A circuit breaker opens after 5 failures / 60 s.
Every call writes an `integration_call_log` row (best-effort, on its own session so
it survives a rolled-back domain transaction). The sidecar response field mapping is
documented inline — adjust it to the exact UNICON build during ops integration.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.integrations.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_PROVIDER = "eimzo"
_OPERATION = "verify_pkcs7"
_VERIFY_PATH = "/api/verify-pkcs7"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)


class ProviderUnavailable(Exception):
    """The E-IMZO sidecar is unreachable/slow/erroring, or the breaker is open."""


@dataclass(frozen=True)
class EimzoSigner:
    """Parsed certificate-subject fields of the signer."""

    org_name: str | None = None
    org_inn: str | None = None       # organisation STIR/INN
    full_name: str | None = None     # holder full name (CN)
    pinfl: str | None = None         # holder PINFL (personal id)
    position: str | None = None      # T (title/position)
    serial_number: str | None = None  # certificate serial


@dataclass(frozen=True)
class EimzoVerifyResult:
    """Normalized outcome of a PKCS#7 verification."""

    ok: bool
    signer: EimzoSigner | None = None
    cert_valid_from: datetime | None = None
    cert_valid_to: datetime | None = None
    revoked: bool | None = None
    error: str | None = None


def _parse_dt(value: Any) -> datetime | None:  # noqa: ANN401 — untrusted sidecar JSON
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_signer(raw: Any) -> EimzoSigner | None:  # noqa: ANN401
    if not isinstance(raw, dict):
        return None
    return EimzoSigner(
        org_name=raw.get("organization") or raw.get("O"),
        org_inn=raw.get("organizationInn") or raw.get("inn") or raw.get("tin"),
        full_name=raw.get("commonName") or raw.get("CN") or raw.get("fullName"),
        pinfl=raw.get("pinfl") or raw.get("PINFL"),
        position=raw.get("position") or raw.get("T"),
        serial_number=raw.get("serialNumber") or raw.get("serial"),
    )


def _signed_data_matches(raw: Any, challenge: str) -> bool:  # noqa: ANN401
    """True if the sidecar-reported signed content equals our challenge.

    Tolerates the sidecar returning the content either as plain text or base64.
    """
    if raw is None:
        return True  # sidecar did not echo it back — rely on its own `valid` verdict
    if not isinstance(raw, str):
        return False
    if raw == challenge:
        return True
    try:
        return base64.b64decode(raw).decode("utf-8", "ignore") == challenge
    except (ValueError, UnicodeDecodeError):
        return False


class EimzoClient:
    """Thin, testable client for the e-imzo-server sidecar verify endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
        breaker: CircuitBreaker | None = None,
        session_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if base_url is None:
            from app.core.config import settings  # noqa: PLC0415 — lazy: import-safe module

            base_url = settings.EIMZO_SERVER_URL
        self._base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=_TIMEOUT))
        self._breaker = breaker or CircuitBreaker()
        self._session_factory = session_factory
        self._clock = clock

    def verify_pkcs7(self, pkcs7_b64: str, challenge: str) -> EimzoVerifyResult:
        """Verify a PKCS#7 signature over `challenge`. Raises ProviderUnavailable on outage."""
        if self._breaker.is_open():
            self._log_call(ok=False, status_code=None, latency_ms=None, error="breaker_open")
            raise ProviderUnavailable("eimzo: circuit open")

        started = self._clock()
        try:
            with self._client_factory() as client:
                resp = client.post(
                    f"{self._base_url}{_VERIFY_PATH}",
                    json={"pkcs7": pkcs7_b64, "challenge": challenge},
                )
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            self._log_call(ok=False, status_code=None, latency_ms=self._elapsed_ms(started), error=type(exc).__name__)
            logger.warning("eimzo.verify.transport_error", extra={"error": str(exc)})
            raise ProviderUnavailable(f"eimzo: {type(exc).__name__}") from exc

        latency_ms = self._elapsed_ms(started)
        if resp.status_code >= 500:
            self._breaker.record_failure()
            self._log_call(ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="sidecar_5xx")
            raise ProviderUnavailable(f"eimzo: sidecar {resp.status_code}")
        if resp.status_code >= 400:
            # A 4xx is a bad request to the sidecar, not an outage — a domain failure.
            self._breaker.record_success()
            self._log_call(ok=False, status_code=resp.status_code, latency_ms=latency_ms, error="sidecar_4xx")
            return EimzoVerifyResult(ok=False, error=f"sidecar_{resp.status_code}")

        # 2xx — a real verdict. The sidecar itself is healthy, so close the breaker.
        self._breaker.record_success()
        self._log_call(ok=True, status_code=resp.status_code, latency_ms=latency_ms, error=None)
        try:
            body = resp.json()
        except ValueError:
            return EimzoVerifyResult(ok=False, error="bad_sidecar_json")
        return self._to_result(body, challenge)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _to_result(self, body: dict[str, Any], challenge: str) -> EimzoVerifyResult:
        valid = bool(body.get("valid") or body.get("success"))
        signer = _parse_signer(body.get("signer") or body.get("subject"))
        result = EimzoVerifyResult(
            ok=valid,
            signer=signer,
            cert_valid_from=_parse_dt(body.get("certNotBefore") or body.get("validFrom")),
            cert_valid_to=_parse_dt(body.get("certNotAfter") or body.get("validTo")),
            revoked=body.get("revoked"),
            error=None if valid else (body.get("error") or "signature_invalid"),
        )
        if not valid:
            return result
        if not _signed_data_matches(body.get("signedData") or body.get("data"), challenge):
            return EimzoVerifyResult(ok=False, signer=signer, error="challenge_mismatch")
        if result.revoked is True:
            return EimzoVerifyResult(ok=False, signer=signer, revoked=True, error="cert_revoked")
        return result

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))

    def _log_call(self, *, ok: bool, status_code: int | None, latency_ms: int | None, error: str | None) -> None:
        """Best-effort integration_call_log row on an isolated session (never raises)."""
        if self._session_factory is None:
            return
        try:
            from app.models.integration import IntegrationCallLog  # noqa: PLC0415

            with self._session_factory() as db:
                db.add(
                    IntegrationCallLog(
                        provider=_PROVIDER,
                        operation=_OPERATION,
                        ok=ok,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001 — call-log write must never break verify
            logger.warning("eimzo.call_log.failed", extra={"error": str(exc)})


# ── Process singleton + module-level convenience ────────────────────────────────

_client: EimzoClient | None = None


def get_eimzo_client() -> EimzoClient:
    """Return the process-wide client (call-logs to the app DB via SessionLocal)."""
    global _client
    if _client is None:
        from app.core.db import SessionLocal  # noqa: PLC0415

        _client = EimzoClient(session_factory=SessionLocal)
    return _client


def _stub_verify(pkcs7_b64: str, challenge: str) -> EimzoVerifyResult:
    """DEV/DEMO verification (settings.EIMZO_STUB) — no sidecar.

    Handles BOTH shapes a developer machine can produce, dispatched on the
    payload itself:

    * the **synthetic envelope** our test bridge emits (base64 JSON) — decoded
      here, enforcing the same challenge-match / revocation rules the real
      sidecar would, so CI and the e2e specs exercise the flow with no device;
    * a **real PKCS#7** from the E-IMZO desktop module (ASN.1, so it opens
      `0x30`) — handed to `local_verify`, which reads the genuine certificate and
      the content it covers but CANNOT check the O'zDSt signature bytes.

    That second branch is why signing with a real token used to fail: this
    function understood only the JSON envelope, so a real DER blob fell into
    `signature_invalid` and told the user their key was bad. See
    `local_verify` for exactly what is and is not checked, and note that
    `EIMZO_STUB` is refused outside DEBUG precisely because of it.
    """
    import json  # noqa: PLC0415

    try:
        payload = base64.b64decode(pkcs7_b64)
    except (ValueError, TypeError):
        return EimzoVerifyResult(ok=False, error="signature_invalid")

    from app.integrations.eimzo import local_verify  # noqa: PLC0415 — avoids a cycle

    if local_verify.looks_like_pkcs7(payload):
        return local_verify.verify_structural(pkcs7_b64, challenge, payload)

    try:
        blob = json.loads(payload)
    except (ValueError, TypeError):
        return EimzoVerifyResult(ok=False, error="signature_invalid")
    if not isinstance(blob, dict) or blob.get("challenge") != challenge:
        return EimzoVerifyResult(ok=False, error="challenge_mismatch")
    signer = EimzoSigner(
        org_name=blob.get("org_name"),
        org_inn=blob.get("tin"),
        full_name=blob.get("name"),
        pinfl=blob.get("pinfl"),
        position=blob.get("position"),
        serial_number=blob.get("serial"),
    )
    if blob.get("revoked"):
        return EimzoVerifyResult(ok=False, signer=signer, revoked=True, error="cert_revoked")
    return EimzoVerifyResult(ok=True, signer=signer, revoked=False)


def verify_pkcs7(pkcs7_b64: str, challenge: str) -> EimzoVerifyResult:
    """Module entry point (see ARCHITECTURE §12) — delegates to the singleton.

    In EIMZO_STUB mode (dev/demo only) it returns a synthetic result instead of
    calling the sidecar.
    """
    from app.core.config import settings  # noqa: PLC0415 — lazy: import-safe module

    if settings.EIMZO_STUB:
        return _stub_verify(pkcs7_b64, challenge)
    return get_eimzo_client().verify_pkcs7(pkcs7_b64, challenge)
