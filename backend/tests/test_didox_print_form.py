"""The operator's printed form — the document as the tax authority renders it.

We show our own WeasyPrint PDF on the contract screen: that is what we ASKED the
parties to sign. Didox renders a different thing — the document as it now stands
at the operator, carrying their electronic-document id and the marks of both
signatures. That second one is what appears in my.soliq.uz, and it is the one a
person actually wants to look at once the rail has done its work.

Two variants of the same endpoint, and the difference is authorisation, not
content: `view/…` additionally checks that the document belongs to the acting
user, so the CABINET uses it (with that company's `user-key`) while STAFF, who
act as nobody, use the plain one with the partner token alone.

Nothing here is downloaded or archived — the archive already lives in S3 as
evidence and no one has asked to fetch it.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest


def _client(handler: Any) -> Any:  # noqa: ANN401
    from app.integrations.didox.client import DidoxClient

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)

    return DidoxClient(
        base_url="https://testapi3.didox.uz",
        partner_token="tok",
        user_key=None,
        client_factory=factory,
    )


class TestWhichEndpointIsCalled:
    def test_a_cabinet_request_goes_through_the_ownership_check(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["user_key"] = request.headers.get("user-key")
            return httpx.Response(200, content=b"%PDF-1.4 ...")

        _client(handler).print_form("8ca0", user_key="uk-1")
        assert "/v1/documents/view/8ca0/pdf/ru" in seen["url"]
        assert seen["user_key"] == "uk-1"

    def test_without_a_user_key_it_uses_the_partner_only_route(self) -> None:
        """Staff act as nobody, so the `view/` variant would refuse them."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, content=b"%PDF-1.4 ...")

        _client(handler).print_form("8ca0")
        assert "/v1/documents/8ca0/pdf/ru" in seen["url"]
        assert "/view/" not in seen["url"]

    def test_the_locale_reaches_the_path(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, content=b"%PDF")

        _client(handler).print_form("8ca0", locale="uz")
        assert seen["url"].endswith("/pdf/uz")


class TestTheBytesComeBackWhole:
    def test_a_pdf_is_returned_raw(self) -> None:
        """A PDF through `resp.json()` is the `/newoffer/base64` mistake again —
        a good 200 turning into an outage at the call site."""
        body = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\nrest-of-a-real-file"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        assert _client(handler).print_form("8ca0") == body

    def test_a_refusal_is_not_mistaken_for_a_document(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"message": "Документ не найден"})

        from app.integrations.didox import DidoxError

        with pytest.raises(DidoxError):
            _client(handler).print_form("8ca0")


def test_the_cabinet_route_is_mounted() -> None:
    """Alongside the other document-scoped routes, which hang off the document id
    rather than the company — either party may open it."""
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/companies/documents/{document_id}/print" in paths
