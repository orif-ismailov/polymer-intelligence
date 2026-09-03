"""A «Договор НК» 007 needs the BUYER's PINFL and FIO too — measured, not assumed.

Our rule ("both parties must have an E-IMZO identity or nothing is sent") was
inferred rather than tested, so on 25.08.2026 we probed it: a 007 addressed to
Didox's own demo company `310529901` («DIDOX TECH») with `Clients[0].FizTin` and
`.Fio` EMPTY.

    POST /v1/documents/007/create/ru  → 200, _id 71f711f8a07611f1b4b01ebdd6719e71

That looked like the rule was too strict, and it was written up that way. **It
was the wrong conclusion, drawn from the wrong endpoint.** On 27.08.2026, once
Didox cleared the ИКПУ gate that had been masking everything behind it, the same
document reached the step that actually judges it:

    POST /v1/documents/{id}/sign      → 422 ПИНФЛ уполномоченного физ.лица
                                            заказчика не указан!;
                                            ФИО уполномоченного физ.лица
                                            заказчика не указано!

So `create` accepts the empty fields and `sign` refuses them. The shipped rule is
right; only its justification was — the fields are required of BOTH parties, not
just of `Owner`. The practical consequence is sharp: a counterparty can only be
on a Didox document if we hold their signer's identity, which means they must be
a verified company in our own cabinet, not merely a TIN in the tax registry.

The lesson generalises past this rule: a provider that validates the same payload
at two steps will teach you the wrong thing if you only reach the first one.
"""

from __future__ import annotations

import pytest


class TestWhatDidoxAcceptsOfTheBuyer:
    def test_a_client_block_without_a_person_is_well_formed(self) -> None:
        """Well-formed but NOT acceptable to `sign` — the shape is right, the
        content is missing.

        Empty rather than invented, and that stays true whatever Didox requires:
        a placeholder person on a document that reaches my.soliq.uz would be a
        false statement about someone real. The fix is to hold the counterparty's
        confirmed identity, never to fill the field in."""
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
