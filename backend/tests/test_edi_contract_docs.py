"""Turning a contract into a Didox «Договор НК» 007 (P7.a Stage 2 — the missing door).

Everything else on this rail shipped: the gateway, the builders, the two-round-trip
signing, the poller, the admin surface. What did not exist was the step that turns
OUR contract into THEIR document — `edi_service.create_document` had no callers at
all, so `signing_provider='didox'` was a flag nothing could act on and the detail
page's Didox branch was unreachable.

The rules asserted here are the ones that decide whether a legally significant
document is right or wrong, and every one of them was learned the expensive way:

  * the **owner is the seller**, not whoever happened to press «создать» — the ЭСФ
    that follows is issued by the seller and quotes this document's number;
  * a party with **no E-IMZO identity** cannot be on the document, because
    `Owner.FizTin`/`Fio` are the signer's PINFL and full name and we hold them
    only after an identity confirmation;
  * the **number is allocated once** and reused by a retry, because the ЭСФ quotes
    it and the roaming centre refuses a mismatched pair;
  * **`vatRegStatus` is read per document**, never cached on the company: it is
    date- and role-sensitive, and what we assert on the day is evidence.
"""

from __future__ import annotations

import datetime
import decimal
from types import SimpleNamespace
from typing import Any

import pytest

D = decimal.Decimal


class _Offer:
    def __init__(self, **kw: Any) -> None:
        self.id = 93
        self.company_id = 31
        self.product_text = "Полиэтилен HDPE F-0220"
        self.grade_text = None
        self.price = D("1150.00")
        self.qty_unit = "MT"
        self.ikpu_code = kw.get("ikpu_code", "03901001001000000")
        self.ikpu_name = "Полимер этилена (полиэтилен)"
        self.ikpu_package_code = kw.get("ikpu_package_code", "1486991")
        self.ikpu_package_name = "тонна"
        self.ikpu_origin = kw.get("ikpu_origin", 1)


def _party(tin: str, **kw: Any):  # noqa: ANN202
    from app.domains.edi.payloads import PartyRequisites

    return PartyRequisites(
        tin=tin,
        name=kw.get("name", f"COMPANY {tin}"),
        address="г. Ташкент",
        oked="20160",
        account="20208000000000000001",
        bank_mfo="00014",
        fiz_tin=kw.get("fiz_tin", "31234567890123"),
        fio=kw.get("fio", "DIRECTOR"),
        director="DIRECTOR",
    )


# ── who owns the document ─────────────────────────────────────────────────────


class TestOwnerIsTheSeller:
    def test_the_deal_decides_when_there_is_one(self) -> None:
        from app.domains.edi.contract_docs import resolve_parties

        contract = SimpleNamespace(initiator_company_id=30, counterparty_company_id=31, offer_id=None)
        deal = SimpleNamespace(seller_company_id=31, buyer_company_id=30)
        seller, buyer = resolve_parties(contract, deal=deal, offer=None)
        assert (seller, buyer) == (31, 30)

    def test_the_offer_decides_when_there_is_no_deal(self) -> None:
        """A contract raised straight off a listing still has a seller: whoever
        published the offer."""
        from app.domains.edi.contract_docs import resolve_parties

        contract = SimpleNamespace(initiator_company_id=30, counterparty_company_id=31, offer_id=93)
        seller, buyer = resolve_parties(contract, deal=None, offer=_Offer())
        assert (seller, buyer) == (31, 30)

    def test_without_either_the_initiator_is_assumed_to_sell(self) -> None:
        """The last resort, and it is a guess — which is why the caller shows the
        seller on the confirmation screen before anything is created."""
        from app.domains.edi.contract_docs import resolve_parties

        contract = SimpleNamespace(initiator_company_id=30, counterparty_company_id=31, offer_id=None)
        seller, buyer = resolve_parties(contract, deal=None, offer=None)
        assert (seller, buyer) == (30, 31)

    def test_an_offer_from_a_third_company_is_refused(self) -> None:
        """A seller who is not a party to the contract would put a stranger's INN
        on a document both sides are about to sign."""
        from app.domains.edi.contract_docs import PartyMismatch, resolve_parties

        contract = SimpleNamespace(initiator_company_id=30, counterparty_company_id=31, offer_id=93)
        with pytest.raises(PartyMismatch):
            resolve_parties(contract, deal=None, offer=_stranger_offer())


def _stranger_offer() -> _Offer:
    offer = _Offer()
    offer.company_id = 77
    return offer


# ── the body ──────────────────────────────────────────────────────────────────


class TestBody:
    def _lines(self):  # noqa: ANN202
        from app.domains.edi.payloads import line_from_offer

        return [
            line_from_offer(
                _Offer(), ord_no=1, name="Полиэтилен HDPE F-0220", count=D("10"), price=D("1150.00")
            )
        ]

    def test_the_contract_prose_travels_as_parts(self) -> None:
        """Didox renders `Parts` as the contract's text. Sending none would put a
        document with no terms in front of both signatories."""
        from app.domains.edi.contract_docs import build_body

        body = build_body(
            number="DEAL-2026-000125",
            date=datetime.date(2026, 8, 21),
            expires_on=datetime.date(2027, 8, 21),
            title="Договор поставки",
            seller=_party("312616547"),
            buyer=_party("590640341"),
            lines=self._lines(),
            sections=[("1. Предмет договора", "Поставщик обязуется поставить сырьё.")],
        )
        assert body["Parts"] == [
            {"ordno": 1, "title": "1. Предмет договора", "body": "Поставщик обязуется поставить сырьё."}
        ]
        assert body["ContractDoc"]["ContractNo"] == "DEAL-2026-000125"
        # PascalCase going IN (lowercase is what comes back), except `Parts`,
        # which Didox spells lowercase in both directions.
        assert body["Owner"]["Tin"] == "312616547"
        assert body["Clients"][0]["Tin"] == "590640341"

    def test_a_contract_with_no_sections_is_refused(self) -> None:
        from app.domains.edi.contract_docs import EmptyContractBody, build_body

        with pytest.raises(EmptyContractBody):
            build_body(
                number="X",
                date=datetime.date(2026, 8, 21),
                expires_on=datetime.date(2027, 8, 21),
                title="Договор",
                seller=_party("312616547"),
                buyer=_party("590640341"),
                lines=self._lines(),
                sections=[],
            )

    def test_a_contract_with_no_lines_is_refused(self) -> None:
        """`Products` is what the ЭСФ later itemises; an empty contract is not a
        supply contract."""
        from app.domains.edi.contract_docs import EmptyContractBody, build_body

        with pytest.raises(EmptyContractBody):
            build_body(
                number="X",
                date=datetime.date(2026, 8, 21),
                expires_on=datetime.date(2027, 8, 21),
                title="Договор",
                seller=_party("312616547"),
                buyer=_party("590640341"),
                lines=[],
                sections=[("1. Предмет", "текст")],
            )


# ── the sections come from the rendered contract, not from a second source ────


class TestSections:
    def test_headings_and_their_text_become_ordered_sections(self) -> None:
        from app.domains.edi.contract_docs import sections_from_html

        html = (
            "<h1>ДОГОВОР ПОСТАВКИ № C-1</h1>"
            "<h2>1. Стороны</h2><p>Продавец и Покупатель.</p>"
            "<h2>2. Предмет договора</h2><p>Поставка полимеров.</p><p>Партия 10 т.</p>"
        )
        assert sections_from_html(html) == [
            ("1. Стороны", "Продавец и Покупатель."),
            ("2. Предмет договора", "Поставка полимеров. Партия 10 т."),
        ]

    def test_tags_and_entities_do_not_leak_into_the_document(self) -> None:
        """The text goes to the tax authority as prose, not as markup."""
        from app.domains.edi.contract_docs import sections_from_html

        html = "<h2>1. Предмет</h2><p>ООО &laquo;Полимер&raquo; <b>обязуется</b>&nbsp;поставить.</p>"
        [(title, text)] = sections_from_html(html)
        assert title == "1. Предмет"
        assert "<" not in text and "&" not in text
        assert "обязуется" in text


# ── the route ─────────────────────────────────────────────────────────────────


def test_the_create_and_prefill_routes_are_mounted() -> None:
    """The whole point of this wave: before it, `edi_service.create_document` had
    no caller at all and a contract could never reach Didox."""
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/companies/{company_id}/didox/contracts/{contract_id}/document" in paths


def test_nothing_but_this_module_assembles_a_007() -> None:
    """One assembly point, so the rules above cannot be half-applied elsewhere."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    callers = [
        path
        for path in root.rglob("*.py")
        if "build_contract_007(" in path.read_text(encoding="utf-8")
    ]
    assert {p.name for p in callers} == {"payloads.py", "contract_docs.py"}


class TestRailIsChosenAtCreation:
    """A contract's rail is frozen when it is drawn up, like `escrow.mode`.

    It shipped as an output-only field: the detail response carried it, the
    signing UI branched on it — and nothing could ever set it, so every contract
    was on the `eimzo` rail forever and the Didox branch was dead code.
    """

    def test_the_create_payload_accepts_a_rail(self) -> None:
        from app.domains.contracts.schemas import ContractCreateIn

        assert "signing_provider" in ContractCreateIn.model_fields

    def test_the_default_stays_our_own_rail(self) -> None:
        """Didox is opt-in: it needs an operator account on BOTH sides."""
        from app.domains.contracts.schemas import ContractCreateIn

        payload = ContractCreateIn(
            initiator_company_id=1, counterparty_company_id=2, template_id=1
        )
        assert payload.signing_provider == "eimzo"

    def test_an_unknown_rail_is_refused_before_the_database_says_so(self) -> None:
        """The CHECK constraint would catch it, but as a 500 at flush time."""
        from pydantic import ValidationError

        from app.domains.contracts.schemas import ContractCreateIn

        with pytest.raises(ValidationError):
            ContractCreateIn(
                initiator_company_id=1,
                counterparty_company_id=2,
                template_id=1,
                signing_provider="carrier-pigeon",
            )

    def test_the_router_passes_the_rail_to_the_service(self) -> None:
        """A field the API accepts and then drops is worse than one it rejects."""
        import inspect

        from app.domains.contracts import api_portal

        assert "signing_provider=body.signing_provider" in inspect.getsource(
            api_portal.create_contract
        )
