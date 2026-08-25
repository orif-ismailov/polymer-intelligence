"""Didox gateway contract (R6 / P7.a — Stage 1).

Didox is Uzbekistan's largest private EDI operator, and `GET /v1/utils/info/{tin}`
is the first thing we use it for: the tax registry's own record of a company,
which fills the registration form and feeds the P7.c verification checks.

The fixtures in this file are **recorded from the live test contour**
(`testapi3.didox.uz`, partner token, 2026-08-15), not invented. Two of them
encode behaviour no amount of reading the docs would have revealed:

  * **"not found" is a 200 with an empty envelope** — every field null or "".
    Passing that through as a snapshot would say "this company is not in the
    state registry", a finding about a real business caused by a sandbox that
    simply has no data for it. It maps to `CompanyNotFound`, never to a DTO.
  * **the test contour answers the lookup with the partner token alone, while
    production demands a `user-key`** (401 `Token expired` with none, 401
    `Invalid user key` with a bad one). So a 401 here is an outage of OUR
    configuration, not a verdict about the company.

Everything else mirrors `test_eimzo_client.py`: the transport is an
`httpx.MockTransport`, nothing touches the network, and the 4xx/5xx split is
asserted through the breaker.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pytest

from app.integrations.circuit_breaker import CircuitBreaker

# ── recorded fixtures ─────────────────────────────────────────────────────────

#: GET testapi3/v1/utils/info/310529901 — a real company (DIDOX TECH itself).
INFO_FOUND: dict[str, Any] = {
    "ns10Code": 26,
    "ns11Code": 8,
    "shortName": '"DIDOX TECH" MCHJ',
    "tin": "310529901",
    "name": '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
    "regDate": "01.06.2023",
    "na1Code": 12,
    "na1Name": "Общество с огр. ответствен.",
    "statusCode": 0,
    "statusName": "Действующие и имеющие налоговые обязательства",
    "mfo": "00401",
    "account": "20208000905656222001",
    "address": "Фидойилар МФЙ, Махтумкули кучаси, 114а-уй  ",
    "oked": "62090",
    "directorTin": "494899720",
    "directorPinfl": "32901930460050",
    "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
    "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
    "isBudget": 0,
    "taxpayerType": 1,
    "isItd": False,
    "personalNum": None,
    "selfEmployment": False,
    "privateNotary": False,
    "peasantFarm": False,
    "VATRegCode": "326080220838",
    "VATRegStatus": 20,
    "VATRegStatusCode": "1110",
    "bankAccount": "20208000905656222001",
    "bankCode": "00401",
    "shortname": '"DIDOX TECH" MCHJ',
    "fullname": '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
    "fullName": '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
}

#: GET testapi3/v1/utils/info/999999999 — HTTP 200, and nothing inside it.
INFO_EMPTY: dict[str, Any] = {
    "ns10Code": None,
    "ns11Code": None,
    "shortName": "",
    "tin": "",
    "name": None,
    "regDate": None,
    "na1Code": None,
    "na1Name": None,
    "statusCode": None,
    "statusName": None,
    "mfo": None,
    "account": None,
    "address": None,
    "oked": None,
    "directorTin": None,
    "directorPinfl": "",
    "director": None,
    "accountant": None,
    "isBudget": 0,
    "taxpayerType": 0,
    "isItd": False,
    "personalNum": None,
    "selfEmployment": False,
    "privateNotary": False,
    "peasantFarm": False,
    "VATRegCode": None,
    "VATRegStatus": None,
    "VATRegStatusCode": "0100",
    "bankAccount": "",
    "bankCode": "",
    "shortname": "",
    "fullname": "",
    "fullName": "",
}

BASE_URL = "https://testapi3.didox.uz"
TOKEN = "partner-token-under-test"  # noqa: S105 — not a credential, a fixture


def _client(handler, *, breaker: CircuitBreaker | None = None, user_key: str | None = None):  # noqa: ANN001, ANN202
    from app.integrations.didox.client import DidoxClient

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    return DidoxClient(
        base_url=BASE_URL,
        partner_token=TOKEN,
        user_key=user_key,
        client_factory=factory,
        breaker=breaker or CircuitBreaker(),
        session_factory=None,
    )


def _ok(payload: Any) -> Any:  # noqa: ANN401
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json=payload)

    return handler


# ── the happy path ────────────────────────────────────────────────────────────


def test_info_by_tin_parses_the_recorded_company() -> None:
    info = _client(_ok(INFO_FOUND)).info_by_tin("310529901")

    assert info is not None
    assert info.tin == "310529901"
    assert info.name == '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT'
    assert info.short_name == '"DIDOX TECH" MCHJ'
    assert info.legal_form == "Общество с огр. ответствен."
    assert info.oked == "62090"
    assert info.bank_mfo == "00401"
    assert info.bank_account == "20208000905656222001"
    assert info.director == "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI"
    assert info.director_pinfl == "32901930460050"
    assert info.vat_reg_code == "326080220838"


def test_the_registration_date_is_read_as_a_date_not_a_string() -> None:
    """Didox writes dd.mm.yyyy; every one of our columns is a real date."""
    info = _client(_ok(INFO_FOUND)).info_by_tin("310529901")

    assert info is not None
    assert info.registered_at == datetime.date(2023, 6, 1)


def test_the_address_is_stripped() -> None:
    """The recorded address carries trailing spaces — they would show up in a form."""
    info = _client(_ok(INFO_FOUND)).info_by_tin("310529901")

    assert info is not None
    assert info.address == "Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"


# ── the empty envelope ────────────────────────────────────────────────────────


def test_an_empty_envelope_is_not_found_rather_than_an_empty_company() -> None:
    """A 200 full of nulls means the registry has no record — not a company with
    no name. Returning a DTO here would put an empty legal name in a form and an
    "unknown" status on a verification check."""
    assert _client(_ok(INFO_EMPTY)).info_by_tin("999999999") is None


def test_a_payload_that_is_not_an_object_is_not_found() -> None:
    assert _client(_ok(["unexpected"])).info_by_tin("310529901") is None


# ── auth headers ──────────────────────────────────────────────────────────────


def test_the_partner_token_rides_on_every_request() -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, json=INFO_FOUND)

    _client(handler).info_by_tin("310529901")

    assert seen[0]["Partner-Authorization"] == TOKEN
    assert "user-key" not in seen[0], "no user key configured — do not send an empty one"


def test_a_user_key_is_sent_when_we_have_one() -> None:
    """Production refuses this endpoint without one; the test contour does not."""
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, json=INFO_FOUND)

    _client(handler, user_key="11111111-2222-3333-4444-555555555555").info_by_tin("310529901")

    assert seen[0]["user-key"] == "11111111-2222-3333-4444-555555555555"


# ── failure modes: the 4xx / 5xx split ────────────────────────────────────────


def test_a_401_is_an_outage_of_our_configuration_not_a_verdict() -> None:
    """Prod answers 401 when the user-key is missing or stale. That says nothing
    about the company, so it must never reach a check as a finding."""
    from app.integrations.didox.client import ProviderUnavailable

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(401, json={"statusCode": 401, "message": "Token expired"})

    with pytest.raises(ProviderUnavailable):
        _client(handler).info_by_tin("310529901")


def test_a_4xx_that_is_our_bad_request_does_not_trip_the_breaker() -> None:
    from app.integrations.didox.client import DidoxError

    breaker = CircuitBreaker(threshold=1)

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(422, json={"data": {"message": "Оферта не подписана"}})

    with pytest.raises(DidoxError):
        _client(handler, breaker=breaker).info_by_tin("310529901")
    assert breaker.is_open() is False, "a 422 is our request, not Didox being down"


def test_a_5xx_is_an_outage_and_opens_the_breaker() -> None:
    from app.integrations.didox.client import ProviderUnavailable

    breaker = CircuitBreaker(threshold=1)

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(503, text="upstream unavailable")

    with pytest.raises(ProviderUnavailable):
        _client(handler, breaker=breaker).info_by_tin("310529901")
    assert breaker.is_open() is True


def test_a_transport_error_is_an_outage() -> None:
    from app.integrations.didox.client import ProviderUnavailable

    breaker = CircuitBreaker(threshold=1)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderUnavailable):
        _client(handler, breaker=breaker).info_by_tin("310529901")
    assert breaker.is_open() is True


def test_an_open_breaker_short_circuits_without_calling() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        return httpx.Response(200, json=INFO_FOUND)

    breaker = CircuitBreaker(threshold=1)
    breaker.record_failure()

    from app.integrations.didox.client import ProviderUnavailable

    with pytest.raises(ProviderUnavailable):
        _client(handler, breaker=breaker).info_by_tin("310529901")
    assert calls == []


def test_unparseable_json_is_not_a_company() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, text="<html>maintenance</html>")

    assert _client(handler).info_by_tin("310529901") is None


# ── the call log ──────────────────────────────────────────────────────────────


class _FakeSession:
    """Records what the call log would have written, without a database."""

    def __init__(self, sink: list[Any]) -> None:
        self.sink = sink

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def add(self, row: Any) -> None:  # noqa: ANN401
        self.sink.append(row)

    def commit(self) -> None:
        self.sink.append("commit")


def test_every_call_writes_an_integration_call_log_row() -> None:
    from app.integrations.didox.client import DidoxClient

    sink: list[Any] = []

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(_ok(INFO_FOUND)), timeout=1.0)

    DidoxClient(
        base_url=BASE_URL,
        partner_token=TOKEN,
        client_factory=factory,
        session_factory=lambda: _FakeSession(sink),
    ).info_by_tin("310529901")

    rows = [row for row in sink if row != "commit"]
    assert len(rows) == 1
    assert rows[0].provider == "didox"
    assert rows[0].operation == "info_by_tin"
    assert rows[0].ok is True
    assert "commit" in sink


def test_a_call_log_failure_never_breaks_the_lookup() -> None:
    from app.integrations.didox.client import DidoxClient

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(_ok(INFO_FOUND)), timeout=1.0)

    def exploding_session() -> Any:  # noqa: ANN401
        raise RuntimeError("no database")

    info = DidoxClient(
        base_url=BASE_URL,
        partner_token=TOKEN,
        client_factory=factory,
        session_factory=exploding_session,
    ).info_by_tin("310529901")

    assert info is not None


# ── catalogs (no user-key needed on either contour) ───────────────────────────


def test_banks_returns_the_mfo_classifier() -> None:
    payload = [{"bankId": "00401", "name": "ТОШКЕНТ Ш."}]
    assert _client(_ok(payload)).banks() == payload


# ── configuration ─────────────────────────────────────────────────────────────


def test_the_partner_token_is_a_conditionally_required_secret() -> None:
    """Empty default, like ESCROW_WEBHOOK_SECRET: the rail is a RUNTIME setting a
    startup validator cannot see, so a mandatory value would burden every
    deployment that never turns Didox on.

    Asserted against the FIELD DEFAULT, not `settings.DIDOX_PARTNER_TOKEN`. The
    resolved value comes from the environment, so reading it here only tested
    "this developer has no `backend/.env`" — which held until someone ran the API
    locally against the test contour, and then failed for a reason unrelated to
    what the test is about.
    """
    from app.core.config import Settings

    assert Settings.model_fields["DIDOX_PARTNER_TOKEN"].default == ""
    assert (
        Settings.model_fields["DIDOX_BASE_URL"].default == "https://testapi3.didox.uz"
    ), "test contour by default"


def test_the_mode_is_a_runtime_setting_shipping_stub() -> None:
    from app.services.settings_service import _SPECS

    spec = _SPECS["didox_mode"]
    assert spec.default == "stub"
    assert spec.choices == ("stub", "live")
