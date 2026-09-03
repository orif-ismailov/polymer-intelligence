"""Didox document rail — gateway contract (P7.a Stage 2 — W3).

Fixtures here are **recorded from the live test contour** on 2026-08-19 during the
W0 spike (partner token, company OOO TREADWAY INC / ИНН 562353400, registered
through the real `test3.didox.uz/registration` form with a real E-IMZO key). Four
of them encode behaviour the published docs get wrong or omit:

  * **`_id` and `document_json.contractid` are DIFFERENT identifiers** — 32 hex
    and 24 hex respectively. Code that conflates them will address the wrong
    document the first time it tries to link an ЭСФ to its договор.
  * **`vatRegStatus` answers `200 {"status": "failed"}`** when it cannot reach
    soliq. A 200 carrying a failure is the worst shape there is: read naively it
    puts an empty VAT registration code on a document that reaches the tax
    authority. `vat_reg_status()` returns `None` for it.
  * **`productClassCodes` can 422 with an upstream cURL error** (`Could not
    resolve host: gnk-gw.didox77.uz`) — their ИКПУ gateway, not our request. The
    envelope is `{"success": false, "error": ...}`, which is a THIRD error shape
    on top of the two Stage 1 already handles.
  * **The archive is a ZIP in the response body** — it must never reach
    `resp.json()`.

Transport is an `httpx.MockTransport`; nothing here touches the network.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.integrations.circuit_breaker import CircuitBreaker

BASE_URL = "https://testapi3.didox.uz"
TOKEN = "partner-token"
USER_KEY = "9a7ec227-9751-4c5e-98fb-442b3edd1e7f"

# ── recorded fixtures ─────────────────────────────────────────────────────────

#: POST /v1/documents/007/create/ru — trimmed to the identifying fields.
CREATE_007: dict[str, Any] = {
    "pending_document": {
        "document_json": {
            "contractdoc": {
                "contractname": "Поставка полимеров",
                "contractno": "SPIKE-0001",
                "contractdate": "2026-08-19",
            },
            "owner": {"tin": "562353400", "name": "OOO TREADWAY INC"},
            "clients": [{"tin": "514890380", "name": "OOO BANCO INC"}],
            "hasvat": True,
            "contractid": "6a8579457a20272c0c01f12a",
            "sellertin": "562353400",
            "buyertin": None,
        }
    },
    "_id": "8ca023ec9bb111f184b91ebdd6719e71",
    "created_date": "2026-08-19 14:37:09",
}

#: GET /v1/documents/{id}?owner=1
GET_DOCUMENT: dict[str, Any] = {
    "data": {
        "json": {"contractdoc": {"contractno": "SPIKE-0001"}, "sellertin": "562353400"},
        "document": {"status": 0},
        "toSign": "MIAGCSqGSIb3DQEHAqCAMIACAQEx",
        "isValid": True,
        "relatedDocuments": [],
        "requestToByResponse": None,
        "attachments": [],
    }
}

#: POST /v1/dsvs/timestamp
TIMESTAMP_OK = {"timeStampTokenB64": "MIAGCSqGSIb3DQEHAqEQ", "success": True, "isAttachedPkcs7": True}

#: GET /v1/profile/vatRegStatus/{tin} — the 200-that-is-a-failure.
VAT_FAILED = {"status": "failed"}
VAT_OK = {"status": "success", "vatRegCode": "326080220838", "vatRegStatus": 20, "vatRegStatusCode": "AAAA"}

#: GET /v1/profile/productClassCodes — their ИКПУ gateway was unreachable.
IKPU_UPSTREAM_DOWN = {
    "success": False,
    "error": (
        "cURL error 6: Could not resolve host: gnk-gw.didox77.uz for "
        "https://gnk-gw.didox77.uz/codes/integration-mxik/company/get/basket-products"
    ),
}
IKPU_OK = {
    "current_page": 1,
    "total": 1,
    "data": [
        {
            "classCode": "02201001001000000",
            "className_ru": "Полиэтилен линейный",
            "usePackage": 1,
            "packages": [{"code": "1505731", "name_ru": "кг", "name": "кг"}],
            "origin": {"id": 1, "name": "Собственное производство"},
        }
    ],
}

#: The offer gate, as documented — a 422 whose context names the missing offer.
OFFER_REQUIRED = {"status": "error", "message": "Оферта не подписана", "context": {"offer": "required"}}


def _client(handler, *, breaker: CircuitBreaker | None = None, user_key: str | None = USER_KEY):  # noqa: ANN001, ANN202
    from app.integrations.didox.client import DidoxClient  # noqa: PLC0415

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


def _json(payload: Any, status: int = 200):  # noqa: ANN001, ANN202, ANN401
    return lambda request: httpx.Response(status, json=payload)


# ── dsvs: timestamp + join ────────────────────────────────────────────────────


class TestDsvs:
    def test_timestamp_sends_both_fields_and_returns_the_token(self) -> None:
        """`signatureHex` is mandatory and camelCase; the pkcs7 field is not.

        This is the leg `capiws.ts` currently makes impossible by discarding
        `signature_hex`, so the naming is worth pinning.
        """
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=TIMESTAMP_OK)

        token = _client(handler).timestamp("PKCS7B64", "deadbeef")
        assert token == "MIAGCSqGSIb3DQEHAqEQ"
        assert seen["path"] == "/v1/dsvs/timestamp"
        assert seen["body"] == {"pkcs7": "PKCS7B64", "signatureHex": "deadbeef"}

    def test_timestamp_without_a_token_is_an_outage_not_a_silent_none(self) -> None:
        from app.integrations.didox.client import ProviderUnavailable  # noqa: PLC0415

        with pytest.raises(ProviderUnavailable):
            _client(_json({"success": False})).timestamp("PKCS7B64", "deadbeef")

    def test_join_signatures_preserves_order(self) -> None:
        """signature1 is THEIRS, signature2 is ours — swapping them silently
        produces a PKCS#7 the tax committee rejects."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"pkcs7B64": "JOINED"})

        assert _client(handler).join_signatures("THEIRS", "OURS") == "JOINED"
        assert seen["body"] == {"signature1": "THEIRS", "signature2": "OURS"}


# ── documents ─────────────────────────────────────────────────────────────────


class TestDocuments:
    def test_create_returns_both_identifiers(self) -> None:
        """`_id` addresses the document; `contractid` links an ЭСФ to it."""
        result = _client(_json(CREATE_007)).create_document("007", {"ContractDoc": {}})
        assert result.didox_id == "8ca023ec9bb111f184b91ebdd6719e71"
        assert result.didox_contract_id == "6a8579457a20272c0c01f12a"
        assert result.document_json["contractdoc"]["contractno"] == "SPIKE-0001"

    def test_create_posts_to_the_doctype_path(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=CREATE_007)

        _client(handler).create_document("002", {"Version": 1}, locale="uz")
        assert seen["path"] == "/v1/documents/002/create/uz"
        assert seen["body"] == {"Version": 1}

    def test_get_document_exposes_the_payload_to_sign(self) -> None:
        """Outgoing signing signs `data.json`; the incoming flow needs `toSign`."""
        doc = _client(_json(GET_DOCUMENT)).get_document("8ca0", owner=1)
        assert doc.json_payload == {
            "contractdoc": {"contractno": "SPIKE-0001"},
            "sellertin": "562353400",
        }
        assert doc.to_sign == "MIAGCSqGSIb3DQEHAqCAMIACAQEx"

    def test_get_document_passes_owner_as_a_query_param(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=GET_DOCUMENT)

        _client(handler).get_document("8ca0", owner=0)
        assert "owner=0" in seen["url"]

    def test_a_bool_owner_still_goes_over_the_wire_as_a_digit(self) -> None:
        """`bool` IS an `int` to the type checker, so `owner=True` type-checks —
        and then httpx renders it `owner=true`, which Didox answers with a bare
        500. Cost a diagnostic cycle on 25.08.2026 that read as their outage."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=GET_DOCUMENT)

        _client(handler).get_document("8ca0", owner=True)  # noqa: FBT003
        assert "owner=1" in seen["url"]
        assert "owner=true" not in seen["url"].lower()

    def test_list_always_sends_page_and_limit(self) -> None:
        """The docs make both mandatory and `/v2/documents` misbehaves without
        them — so they are not optional keyword arguments that might be omitted."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json={"data": [], "total": 0})

        _client(handler).list_documents(date_from_updated="2026-08-01")
        assert seen["params"]["page"] == "1"
        assert seen["params"]["limit"] == "50"
        assert seen["params"]["dateFromUpdated"] == "2026-08-01"

    def test_archive_returns_bytes_not_json(self) -> None:
        """The evidence pack is a ZIP in the body. Routing it through
        `resp.json()` would raise on the first real archive we ever fetch."""
        blob = b"PK\x03\x04zipbytes"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/documents/8ca0/archive"
            return httpx.Response(200, content=blob)

        assert _client(handler).archive("8ca0") == blob

    def test_sign_sends_the_signature_field(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": True})

        _client(handler).sign_document("8ca0", "TIMESTAMPED")
        assert seen["path"] == "/v1/documents/8ca0/sign"
        assert seen["body"] == {"signature": "TIMESTAMPED"}

    def test_send_is_a_put_and_the_door_a_draft_actually_uses(self) -> None:
        """`POST /{id}/sign` is not the way out of a draft.

        Live on testapi3 it answers **500 `Undefined variable $isDraft`** — a
        leaked PHP error, the same for a real timestamped signature and for
        garbage. Their own 405 named the working route: `PUT /{id}/send`, which
        answers a real business refusal («подпишите публичную оферту») instead of
        a stack trace. Recorded 21.08.2026.
        """
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": True})

        result = _client(handler).send_document("8ca0", "TIMESTAMPED")
        assert seen["method"] == "PUT"
        assert seen["path"] == "/v1/documents/8ca0/send"
        assert seen["body"] == {"signature": "TIMESTAMPED"}
        assert result.ok is True

    def test_send_surfaces_the_unsigned_offer_refusal(self) -> None:
        """The refusal that actually blocks the rail today, verbatim from them."""
        from app.integrations.didox import DidoxError

        message = (
            "Настоящим уведомляем вас, что с 01.07.2023 услуги сервиса Didox будут "
            "оказываться от лица OOO “Didox Tech”. ... Для успешной отправки документов, "
            "необходимо подписать условия публичной оферты на сайте didox.uz"
        )
        with pytest.raises(DidoxError) as exc:
            _client(_json({"status": "error", "message": message}, status=422)).send_document(
                "8ca0", "TIMESTAMPED"
            )
        assert exc.value.offer_not_signed is True

    def test_a_200_may_still_carry_a_warning(self) -> None:
        """`warningDetails` means the tax committee accepted WITH remarks. It is
        not a failure and must not be raised as one."""
        result = _client(_json({"data": True, "warningDetails": {"code": "W1"}})).sign_document(
            "8ca0", "TIMESTAMPED"
        )
        assert result.ok is True
        assert result.warning == {"code": "W1"}


# ── error taxonomy ────────────────────────────────────────────────────────────


class TestErrors:
    def test_offer_not_signed_is_recognisable(self) -> None:
        """It reads like a document problem and is actually a one-time onboarding
        step, so the caller must be able to tell it apart without regex."""
        from app.integrations.didox.client import DidoxError  # noqa: PLC0415

        with pytest.raises(DidoxError) as exc:
            _client(_json(OFFER_REQUIRED, 422)).create_document("007", {})
        assert exc.value.offer_not_signed is True

    def test_an_ordinary_422_is_not_an_offer_problem(self) -> None:
        from app.integrations.didox.client import DidoxError  # noqa: PLC0415

        with pytest.raises(DidoxError) as exc:
            _client(_json({"status": "error", "message": "Неподдерживаемый тип"}, 422)).create_document(
                "041", {}
            )
        assert exc.value.offer_not_signed is False

    def test_the_success_false_envelope_surfaces_its_error_text(self) -> None:
        """A third error shape, seen live on the ИКПУ endpoint. Without this the
        message degrades to the HTTP reason phrase and the upstream host — the
        one fact that explains the failure — is lost."""
        from app.integrations.didox.client import DidoxError  # noqa: PLC0415

        with pytest.raises(DidoxError) as exc:
            _client(_json(IKPU_UPSTREAM_DOWN, 422)).product_class_codes(search="полиэтилен")
        assert "gnk-gw.didox77.uz" in exc.value.message

    def test_5xx_trips_the_breaker_but_422_does_not(self) -> None:
        from app.integrations.didox.client import DidoxError, ProviderUnavailable  # noqa: PLC0415

        breaker = CircuitBreaker(threshold=2)
        client = _client(_json({"status": "error", "message": "nope"}, 422), breaker=breaker)
        for _ in range(3):
            with pytest.raises(DidoxError):
                client.sign_document("8ca0", "X")
        assert breaker.is_open() is False

        breaker = CircuitBreaker(threshold=2)
        client = _client(_json({}, 500), breaker=breaker)
        for _ in range(2):
            with pytest.raises(ProviderUnavailable):
                client.sign_document("8ca0", "X")
        assert breaker.is_open() is True


# ── profile: ИКПУ + VAT ───────────────────────────────────────────────────────


class TestProfile:
    def test_vat_reg_status_failure_envelope_is_not_data(self) -> None:
        """`{"status": "failed"}` arrives with HTTP 200. Returning a DTO with
        empty fields here would put a blank VAT code on an ЭСФ."""
        assert _client(_json(VAT_FAILED)).vat_reg_status("562353400") is None

    def test_vat_reg_status_success_is_parsed(self) -> None:
        vat = _client(_json(VAT_OK)).vat_reg_status("562353400")
        assert vat is not None
        assert vat.code == "326080220838"
        assert vat.status == 20

    def test_vat_reg_status_passes_date_and_role(self) -> None:
        """Both change the answer — it is a point-in-time, per-role fact."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=VAT_OK)

        _client(handler).vat_reg_status("562353400", document_date="2026-08-19", is_seller=True)
        assert seen["params"]["document_date"] == "2026-08-19"
        assert seen["params"]["isSeller"] == "true"

    def test_product_class_codes_flattens_packages_and_origin(self) -> None:
        rows = _client(_json(IKPU_OK)).product_class_codes(search="полиэтилен")
        assert len(rows) == 1
        row = rows[0]
        assert row.class_code == "02201001001000000"
        assert row.origin_id == 1
        assert row.packages == [("1505731", "кг")]


class TestBareBase64Endpoints:
    """`/v1/newoffer/base64` and `/documentBase64` answer with RAW text.

    No envelope, no quotes — just the base64. The first version of this client
    sent them through `resp.json()`, which failed and surfaced as
    `didox_unavailable`: the onboarding step reported an outage while Didox had
    answered 200 with a perfectly good PDF. The original unit test passed because
    its fixture was JSON; only running it against the live contour exposed it.
    """

    def test_a_bare_base64_body_is_returned_verbatim(self) -> None:
        pdf = "JVBERi0xLjUKJeLjz9MKMTggMCBvYmo="

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/newoffer/base64"
            return httpx.Response(200, content=pdf.encode())

        assert _client(handler).offer_base64() == pdf

    def test_a_wrapped_body_is_also_accepted(self) -> None:
        """Some deployments envelope it; both shapes must work."""
        pdf = "JVBERi0xLjUK"
        assert _client(_json({"data": pdf})).offer_base64() == pdf

    def test_document_base64_reads_the_same_way(self) -> None:
        blob = "MIAGCSqGSIb3DQEHAqCAMIACAQEx"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/documents/8ca0/documentBase64"
            return httpx.Response(200, content=blob.encode())

        assert _client(handler).document_base64("8ca0") == blob

    def test_an_empty_body_is_still_an_outage(self) -> None:
        from app.integrations.didox.client import ProviderUnavailable  # noqa: PLC0415

        with pytest.raises(ProviderUnavailable):
            _client(lambda r: httpx.Response(200, content=b"")).offer_base64()


class TestOfferCreateQuirks:
    """`POST /v1/documents/offer/create` does not behave like the rest of the API.

    Both facts here were established live on testapi3 (21–24.08.2026) and cost a
    day between them.
    """

    def test_the_partner_token_goes_bare_on_every_call(self) -> None:
        """This endpoint JWT-verifies the HEADER VALUE, so the `Bearer ` prefix
        every other API expects makes it answer `500 JsonWebTokenError: invalid
        token`. We send the token bare everywhere, which happens to satisfy both —
        and this test exists so nobody "fixes" it by adding the prefix."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("partner-authorization")
            return httpx.Response(200, json={"pending_document": {"document_json": {"a": 1}}})

        _client(handler).create_offer_document("JVBERi0=", tax_id="312616547")
        assert seen["auth"] == TOKEN
        assert not seen["auth"].lower().startswith("bearer")

    def test_the_body_carries_the_company_tin_didox_asked_for(self) -> None:
        """Didox support, 24.08.2026: «taxIdOrPinfl ташкилотингиз ИНН кийматини
        толдириб кайта юбориб куринг». It does NOT fix their `Failed to store
        offer` (verified with and without, in six spellings), but it is what they
        asked for and the field passes their validator."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"pending_document": {"document_json": {"a": 1}}})

        _client(handler).create_offer_document("JVBERi0=", tax_id="312616547")
        assert seen["body"] == {"document": "JVBERi0=", "taxIdOrPinfl": "312616547"}
