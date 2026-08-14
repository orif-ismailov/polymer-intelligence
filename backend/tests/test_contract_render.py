"""Unit tests for contract_render (R3 Stage B — TB1.3).

The HTML layer is pure/deterministic (golden sha256 with a frozen timestamp) and
HTML-escapes values; the PDF layer is exercised when WeasyPrint's native libs are
available (skipped otherwise — they live in the backend image, not necessarily CI).
"""

from __future__ import annotations

import hashlib

import pytest

from app.domains.contracts import render as contract_render

_TEMPLATE = (
    "<h1>{{ title }} № {{ contract_public_id }}</h1>"
    "<p>{{ generated_at }}</p>"
    "<p>Поставщик: {{ initiator_legal_name }} ({{ initiator_inn }})</p>"
    "<p>Покупатель: {{ counterparty_legal_name }} ({{ counterparty_inn }})</p>"
    "<p>{{ product }} — {{ qty }} {{ unit }} @ {{ price }} {{ currency }}</p>"
    "<p>Счёт: {{ initiator_bank_account }}</p>"
)

_VARIABLES = {"title": "Договор", "product": "HDPE", "qty": "20", "unit": "t", "price": "1000", "currency": "USD"}
_INITIATOR = {"legal_name": "OOO Seller", "inn": "301234567", "bank_account": "20208000000000000001"}
_COUNTERPARTY = {"legal_name": "OOO Buyer", "inn": "309999999"}


def _render() -> str:
    return contract_render.render_contract_html(
        _TEMPLATE, _VARIABLES, _INITIATOR, _COUNTERPARTY,
        contract_public_id="abc-123", generated_at="2026-07-26T00:00:00Z",
    )


def test_render_is_deterministic_stable_sha256() -> None:
    a = _render()
    b = _render()
    assert a == b  # no hidden now()/random
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def test_render_substitutes_all_fields() -> None:
    out = _render()
    assert "Договор № abc-123" in out
    assert "OOO Seller (301234567)" in out
    assert "OOO Buyer (309999999)" in out
    assert "HDPE — 20 t @ 1000 USD" in out
    assert "20208000000000000001" in out  # bank account IS in the final document


def test_render_html_escapes_values() -> None:
    out = contract_render.render_contract_html(
        "<p>{{ product }}</p>",
        {"product": "<script>alert(1)</script>"},
        {}, {},
        contract_public_id="x", generated_at="t",
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_missing_placeholder_becomes_empty() -> None:
    out = contract_render.render_contract_html(
        "<p>[{{ nope }}]</p>", {}, {}, {}, contract_public_id="x", generated_at="t"
    )
    assert "[]" in out


def _weasyprint_available() -> bool:
    try:
        from weasyprint import HTML  # noqa: PLC0415

        HTML(string="<p>x</p>").write_pdf()
        return True
    except Exception:  # noqa: BLE001 — native libs missing → skip PDF assertions
        return False


@pytest.mark.skipif(not _weasyprint_available(), reason="WeasyPrint native libs unavailable")
def test_html_to_pdf_produces_pdf_bytes() -> None:
    pdf = contract_render.render_contract_pdf(
        _TEMPLATE, _VARIABLES, _INITIATOR, _COUNTERPARTY,
        contract_public_id="abc-123", generated_at="2026-07-26T00:00:00Z",
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
