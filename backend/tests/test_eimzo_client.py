"""Unit tests for the E-IMZO gateway adapter (R3 TA1.2).

All network I/O is stubbed with httpx.MockTransport (no sidecar, no DB — session
logging is disabled). Covers: valid signature, invalid signature, challenge
mismatch, revoked cert, transport timeout → ProviderUnavailable, 5xx → outage,
4xx → domain failure (no trip), and breaker-open short-circuit.
"""

from __future__ import annotations

import httpx
import pytest

from app.integrations.circuit_breaker import CircuitBreaker
from app.integrations.eimzo.client import EimzoClient, ProviderUnavailable

_VALID_BODY = {
    "valid": True,
    "signedData": "chal-123",
    "signer": {
        "organization": "OOO Polymer Trade",
        "organizationInn": "301234567",
        "commonName": "IVANOV IVAN",
        "pinfl": "31234567890123",
        "position": "Director",
        "serialNumber": "AABBCC",
    },
    "certNotBefore": "2024-01-01T00:00:00Z",
    "certNotAfter": "2027-01-01T00:00:00Z",
    "revoked": False,
}


def _client(handler, *, breaker: CircuitBreaker | None = None) -> EimzoClient:  # noqa: ANN001
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    return EimzoClient(
        base_url="http://eimzo-server:8080",
        client_factory=factory,
        breaker=breaker or CircuitBreaker(),
        session_factory=None,  # no DB in unit tests
    )


def test_valid_signature_parses_signer() -> None:
    client = _client(lambda req: httpx.Response(200, json=_VALID_BODY))
    result = client.verify_pkcs7("cGtjczc=", "chal-123")
    assert result.ok is True
    assert result.signer is not None
    assert result.signer.org_inn == "301234567"
    assert result.signer.full_name == "IVANOV IVAN"
    assert result.signer.pinfl == "31234567890123"
    assert result.signer.position == "Director"
    assert result.revoked is False
    assert result.cert_valid_to is not None and result.cert_valid_to.year == 2027


def test_invalid_signature_returns_not_ok() -> None:
    client = _client(lambda req: httpx.Response(200, json={"valid": False, "error": "bad_sig"}))
    result = client.verify_pkcs7("x", "chal")
    assert result.ok is False
    assert result.error == "bad_sig"


def test_challenge_mismatch() -> None:
    body = {**_VALID_BODY, "signedData": "a-different-nonce"}
    client = _client(lambda req: httpx.Response(200, json=body))
    result = client.verify_pkcs7("x", "chal-123")
    assert result.ok is False
    assert result.error == "challenge_mismatch"


def test_signed_data_base64_variant_matches() -> None:
    # sidecar echoes the signed content base64-encoded
    body = {**_VALID_BODY, "signedData": "Y2hhbC0xMjM="}  # base64("chal-123")
    client = _client(lambda req: httpx.Response(200, json=body))
    result = client.verify_pkcs7("x", "chal-123")
    assert result.ok is True


def test_revoked_cert_is_failure() -> None:
    body = {**_VALID_BODY, "revoked": True}
    client = _client(lambda req: httpx.Response(200, json=body))
    result = client.verify_pkcs7("x", "chal-123")
    assert result.ok is False
    assert result.error == "cert_revoked"
    assert result.revoked is True


def test_timeout_raises_provider_unavailable_and_trips_failure() -> None:
    breaker = CircuitBreaker(threshold=1)

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=req)

    client = _client(handler, breaker=breaker)
    with pytest.raises(ProviderUnavailable):
        client.verify_pkcs7("x", "chal")
    assert breaker.is_open() is True  # threshold=1 → tripped


def test_5xx_raises_provider_unavailable() -> None:
    client = _client(lambda req: httpx.Response(503, text="upstream down"))
    with pytest.raises(ProviderUnavailable):
        client.verify_pkcs7("x", "chal")


def test_4xx_is_domain_failure_not_outage() -> None:
    breaker = CircuitBreaker()
    client = _client(lambda req: httpx.Response(422, text="bad pkcs7"), breaker=breaker)
    result = client.verify_pkcs7("x", "chal")
    assert result.ok is False
    assert result.error == "sidecar_422"
    assert breaker.is_open() is False  # a 4xx does not trip the breaker


class _FakeSession:
    """Minimal session context manager capturing added rows + commits."""

    def __init__(self, sink: list) -> None:  # noqa: ANN001
        self._sink = sink

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def add(self, row: object) -> None:
        self._sink.append(row)

    def commit(self) -> None:
        self._sink.append("commit")


def test_writes_integration_call_log_on_success() -> None:
    rows: list = []
    client = EimzoClient(
        base_url="http://eimzo-server:8080",
        client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=_VALID_BODY)),
            timeout=1.0,
        ),
        breaker=CircuitBreaker(),
        session_factory=lambda: _FakeSession(rows),
    )
    client.verify_pkcs7("x", "chal-123")
    logged = [r for r in rows if r != "commit"]
    assert len(logged) == 1
    assert logged[0].provider == "eimzo"
    assert logged[0].operation == "verify_pkcs7"
    assert logged[0].ok is True
    assert "commit" in rows


def test_open_breaker_short_circuits_without_calling() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("refused", request=req)

    breaker = CircuitBreaker(threshold=5, window=60.0, cooldown=60.0)
    client = _client(handler, breaker=breaker)
    for _ in range(5):
        with pytest.raises(ProviderUnavailable):
            client.verify_pkcs7("x", "chal")
    assert breaker.is_open() is True
    calls_after_open = calls["n"]
    # 6th call must short-circuit — no new transport call.
    with pytest.raises(ProviderUnavailable):
        client.verify_pkcs7("x", "chal")
    assert calls["n"] == calls_after_open
