"""The BUYER's block comes from the tax registry; the SELLER's comes from us.

Settled live on 27.08.2026, and it is the finding that unblocked the whole rail.

We had assumed the counterparty's PINFL could only come from an E-IMZO identity
confirmation in our own cabinet, and therefore that only a verified user of ours
could ever be on a Didox document. That assumption cost two days and was simply
wrong: `GET /v1/utils/info/{tin}` returns `directorPinfl`, `director`, `oked`,
`account`, `mfo` and the VAT code for ANY company in the state registry. Built
`Clients[0]` entirely from that answer and the document went through —
`434b8502a1fa11f18ee61ebdd6719e71`, status 1, awaiting the partner's signature.

The split that follows is not a convenience, it is about who vouches for what:

  * the **seller** is `Owner`, signs here, with a key we watched them use — so
    their block comes from OUR records and their identity confirmation;
  * the **buyer** signs at their own operator and may not be our user at all —
    so their block comes from the registry the tax authority itself keeps, which
    is a stronger source than anything we could hold about a stranger.

Nothing is guessed in either direction: a registry that cannot answer raises.
"""

from __future__ import annotations

from typing import Any

import pytest


def _registry_row(**overrides: Any) -> Any:  # noqa: ANN401
    from app.integrations.didox.client import DidoxCompanyInfo

    fields: dict[str, Any] = {
        "tin": "310529901",
        "name": '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
        "address": "Фидойилар МФЙ, Махтумкули кучаси, 114а-уй  ",
        "oked": "62090",
        "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
        "director_pinfl": "32901930460050",
        "bank_mfo": "00401",
        "bank_account": "20208000905656222001",
        "vat_reg_code": "326080220838",
        "vat_reg_status": 20,
    }
    fields.update(overrides)
    return DidoxCompanyInfo(**fields)


class _Registry:
    def __init__(self, row: Any = None, raises: Exception | None = None) -> None:  # noqa: ANN401
        self.row = row
        self.raises = raises
        self.asked: list[str] = []

    def info_by_tin(self, tin: str) -> Any:  # noqa: ANN401
        self.asked.append(tin)
        if self.raises is not None:
            raise self.raises
        return self.row


class TestPartyFromRegistry:
    def test_every_field_the_document_needs_is_taken_from_the_answer(self) -> None:
        from app.domains.edi.contract_docs import party_from_registry

        party = party_from_registry(_Registry(_registry_row()), "310529901")
        assert party.tin == "310529901"
        assert party.fiz_tin == "32901930460050"
        assert party.fio == "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI"
        assert party.oked == "62090"
        assert party.account == "20208000905656222001"
        assert party.bank_mfo == "00401"

    def test_the_address_is_trimmed(self) -> None:
        """The registry pads it; a trailing double space in a legal document is
        the kind of thing that reads as carelessness."""
        from app.domains.edi.contract_docs import party_from_registry

        party = party_from_registry(_Registry(_registry_row()), "310529901")
        assert party.address == "Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"

    def test_a_company_the_registry_does_not_know_raises(self) -> None:
        """`ИНН/ПИНФЛ заказчика некорректный` is what Didox answers for these —
        better to stop before a key is loaded than after."""
        from app.domains.edi.contract_docs import CounterpartyNotInRegistry, party_from_registry

        with pytest.raises(CounterpartyNotInRegistry):
            party_from_registry(_Registry(None), "562353400")

    def test_a_registry_outage_raises_rather_than_inventing_a_party(self) -> None:
        from app.domains.edi.contract_docs import CounterpartyNotInRegistry, party_from_registry
        from app.integrations.didox import ProviderUnavailable

        with pytest.raises(CounterpartyNotInRegistry):
            party_from_registry(_Registry(raises=ProviderUnavailable("down")), "310529901")

    def test_a_record_without_a_signer_is_refused(self) -> None:
        """An empty `directorPinfl` fails Didox's own validator at `sign`, after
        the password — so it is refused here instead."""
        from app.domains.edi.contract_docs import CounterpartyNotInRegistry, party_from_registry

        with pytest.raises(CounterpartyNotInRegistry):
            party_from_registry(_Registry(_registry_row(director_pinfl=None)), "310529901")


class TestTheDocumentUsesBothSources:
    def test_the_assembler_reads_the_registry_for_the_buyer(self) -> None:
        import inspect

        from app.domains.edi import contract_docs

        source = inspect.getsource(contract_docs.create_for_contract)
        assert "party_from_registry" in source

    def test_the_seller_still_comes_from_our_own_records(self) -> None:
        import inspect

        from app.domains.edi import contract_docs

        source = inspect.getsource(contract_docs.create_for_contract)
        assert "party_from_company" in source

    def test_the_buyer_no_longer_needs_a_confirmed_identity_here(self) -> None:
        """`signer_identity_missing:<buyer>` was a wall with nothing behind it:
        a counterparty who is not our user cannot confirm anything in our
        cabinet, and does not have to — the registry answers for them."""
        import inspect

        from app.domains.edi import api_portal

        source = inspect.getsource(api_portal._prefill)  # noqa: SLF001
        assert "for party_id in (seller_id, buyer_id)" not in source
