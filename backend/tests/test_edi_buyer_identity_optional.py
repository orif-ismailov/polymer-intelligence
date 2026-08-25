"""What a «Договор НК» 007 actually needs of the BUYER — measured, not assumed.

Probed live on 25.08.2026 against `testapi3`, because the shipped rule ("both
parties must have an E-IMZO identity or nothing is sent") was never tested
against the provider — it was inferred from the fact that `Owner.FizTin`/`Fio`
are mandatory, and `Owner` is the seller.

The probe: a 007 addressed to Didox's own demo company `310529901`
(«DIDOX TECH») with `Clients[0].FizTin` and `.Fio` EMPTY.

    POST /v1/documents/007/create/ru  → 200, _id 71f711f8a07611f1b4b01ebdd6719e71

So the operator does not need the buyer's PINFL. What it DOES need is the buyer's
ИКПУ basket — `/sign` then answered `[03902001002000002] не включены в список
избранных ИКПУ!`, and `class_packages` confirms the code for the seller and
refuses it for the buyer.

These tests pin the FACTS. Whether our own `_prefill` should stop demanding a
buyer identity is a product decision that has not been taken — it is recorded as
an open question in `.planning/deal-lifecycle/P7-PROVIDERS-LIVE.md`, not asserted
here, so nothing in this file will quietly go red when it is.
"""

from __future__ import annotations

import pytest


class TestWhatDidoxAcceptsOfTheBuyer:
    def test_a_client_block_without_a_person_is_well_formed(self) -> None:
        """Empty, not absent and not invented: a placeholder name on a document
        that reaches my.soliq.uz would be a false statement about a real person."""
        from app.domains.edi.payloads import PartyRequisites, _party_007

        party = PartyRequisites(
            tin="310529901",
            name='"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
            address=None,
            oked=None,
            account=None,
            bank_mfo=None,
            fiz_tin=None,
            fio=None,
            director=None,
        )
        block = _party_007(party)
        assert block["Tin"] == "310529901"
        assert block["FizTin"] == ""
        assert block["Fio"] == ""

    def test_the_seller_side_still_refuses_to_go_out_unidentified(self) -> None:
        """`Owner.FizTin`/`Fio` ARE the subject of the signature we produce, and
        we hold them only after an identity confirmation in this cabinet."""
        import inspect

        from app.domains.edi import contract_docs

        assert "SignerIdentityMissing" in inspect.getsource(contract_docs.party_from_company)


@pytest.mark.parametrize(
    ("tin", "what"),
    [
        ("310529901", "DIDOX TECH — принят как заказчик"),
        ("302936161", "VENKON GROUP — есть в реестре"),
    ],
)
def test_the_counterparties_that_work_are_written_down(tin: str, what: str) -> None:
    """Which counterparties `testapi3` actually accepts cost a day to establish.
    That belongs in the repo, where the next person will look, not in a chat."""
    import pathlib

    report = (
        pathlib.Path(__file__).resolve().parents[2] / "docs/didox-support-report.md"
    ).read_text(encoding="utf-8")
    assert tin in report, what
