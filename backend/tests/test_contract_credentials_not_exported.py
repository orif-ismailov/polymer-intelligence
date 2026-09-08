"""The cabinet credentials printed in a contract must never reach Didox.

`SUPPLY_V2` prints a login and a password on the contract the two parties sign. The
same rendered HTML is the source for the Didox «Договор» (007) payload — `contract_docs`
lifts every `<h2>` section out of it — and that document goes to the tax authority and
is printed on the my.soliq.uz form. So a placement mistake here does not fail, does not
log, and does not look wrong in the PDF: it publishes a customer's password.

Two properties are asserted, because the block is protected twice:

1. it sits ABOVE the first `<h2>`, which `_SECTION.finditer` never reaches, and
2. it is marked `data-didox="skip"`, which `sections_from_html` strips first.

**Read against the SHIPPED template file**, not an inline fixture. An inline fixture is
precisely the test that stays green while `supply_v2_ru.html` leaks — the fixture is not
what gets rendered for a real contract.
"""

from __future__ import annotations

import datetime
import decimal
import json
from pathlib import Path

import pytest

from app.domains.contracts.render import render_contract_html
from app.domains.edi.contract_docs import sections_from_html

_TEMPLATE = (
    Path(__file__).parent.parent
    / "app"
    / "seed"
    / "data"
    / "contract_templates"
    / "supply_v2_ru.html"
)

_LOGIN = "SENTINEL-LOGIN-a1b2c3"
_PASSWORD = "SENTINEL-PASSWORD-d4e5f6"


@pytest.fixture(scope="module")
def rendered() -> str:
    """The real template, rendered the way `contract_service` renders it."""
    return render_contract_html(
        _TEMPLATE.read_text(encoding="utf-8"),
        contract_public_id="TEST-0001",
        generated_at="08.09.2026",
        initiator={"legal_name": "ООО Поставщик", "inn": "123456789"},
        counterparty={"legal_name": "ООО Покупатель", "inn": "987654321"},
        variables={
            "product": "ПВХ С-6669",
            "qty": "20",
            "unit": "t",
            "price": "1000",
            "currency": "USD",
            "incoterms": "EXW",
            "payment_terms": "100% предоплата",
            "delivery_window": "октябрь 2026",
            "portal_login": _LOGIN,
            "portal_password": _PASSWORD,
        },
    )


def test_the_credentials_are_actually_on_the_contract(rendered: str) -> None:
    """First things first: the block renders. A leak test over an empty block passes."""
    assert _LOGIN in rendered
    assert _PASSWORD in rendered


def test_no_didox_section_carries_the_credentials(rendered: str) -> None:
    sections = sections_from_html(rendered)
    assert sections, "the template should still produce sections for the 007 payload"

    for title, body in sections:
        assert _LOGIN not in title and _LOGIN not in body
        assert _PASSWORD not in title and _PASSWORD not in body


def test_the_credentials_survive_neither_guard_being_relied_on_alone(rendered: str) -> None:
    """Each protection holds on its own, so losing one is not a disclosure.

    Removing the marker (someone tidies the HTML) leaves the placement; moving the
    block below a heading leaves the marker. Both are checked here because the failure
    is silent either way.
    """
    # 1. Placement: the block is above the first <h2>.
    assert rendered.index(_PASSWORD) < rendered.index("<h2")

    # 2. Marker: with the block moved to the very end — the tempting spot, next to the
    #    signatures — the strip still keeps it out.
    block_start = rendered.index('<div class="access"')
    block_end = rendered.index("</div>", block_start) + len("</div>")
    block = rendered[block_start:block_end]
    moved = rendered[:block_start] + rendered[block_end:] + block
    for title, body in sections_from_html(moved):
        assert _PASSWORD not in title and _PASSWORD not in body


def test_the_007_payload_does_not_contain_the_credentials(rendered: str) -> None:
    """End of the line: the JSON that actually goes over the wire to Didox."""
    from app.domains.edi.contract_docs import build_body  # noqa: PLC0415
    from app.domains.edi.payloads import DocumentLine, PartyRequisites  # noqa: PLC0415

    party = PartyRequisites(
        tin="123456789",
        name="ООО Поставщик",
        address="Ташкент",
        account="20208000000000000001",
        bank_mfo="00014",
        fiz_tin="12345678901234",
        fio="Иванов И.И.",
    )
    payload = build_body(
        number="TEST-0001",
        date=datetime.date(2026, 9, 8),
        expires_on=datetime.date(2027, 9, 8),
        title="Договор поставки",
        seller=party,
        buyer=party,
        lines=[
            DocumentLine(
                ord_no=1,
                name="ПВХ С-6669",
                catalog_code="01234567890123456",
                catalog_name="ПВХ",
                package_code="1",
                package_name="кг",
                count=decimal.Decimal("20"),
                price=decimal.Decimal("1000"),
            )
        ],
        sections=sections_from_html(rendered),
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    assert _LOGIN not in serialized
    assert _PASSWORD not in serialized
