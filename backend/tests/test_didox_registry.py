"""Didox as a state-registry channel (R6 / P7.a — Stage 1).

P7.c shipped the whole registry seam — the `GovRegistryClient` protocol, the
normalized DTOs, the append-only `registry_snapshots` table, the two pure check
functions and the operator UI — with `StubGovRegistryClient` behind it, because
ПЦД access never arrived. Didox's `/v1/utils/info/{tin}` is that missing channel:
it answers with the tax registry's own record, so it plugs into the existing
protocol rather than starting a second one.

What these tests hold in place:

  * **A company Didox has no record of is `CompanyNotFound`, which IS a
    `ProviderUnavailable`.** That inheritance is the whole design: every existing
    caller already degrades `ProviderUnavailable` to "no snapshot" → an
    `unavailable` check → the manual path stays open, while the lookup endpoint
    catches the narrower type and tells the form "not found". Neither one invents
    a finding about a real business out of a sandbox gap.
  * **`lookup_licenses` raises.** Didox carries no licence data, and an empty
    list would read as "this company holds no licences" — the exact lie
    `StubGovRegistryClient` was written to avoid.
  * **`gov_registry_mode` still ships `stub`.** Turning the channel on is an
    operator decision, not a side effect of deploying this code.
"""

from __future__ import annotations

import datetime

import pytest

from tests.test_didox_client import INFO_EMPTY, INFO_FOUND


class _FakeDidox:
    """A Didox client that answers with whatever the test hands it."""

    def __init__(self, info: object = None, *, raises: Exception | None = None) -> None:
        self.info = info
        self.raises = raises
        self.asked: list[str] = []

    def info_by_tin(self, tin: str, *, user_key: str | None = None) -> object:  # noqa: ARG002
        self.asked.append(tin)
        if self.raises is not None:
            raise self.raises
        return self.info


def _info(payload: dict[str, object]):  # noqa: ANN202
    from app.integrations.didox.client import DidoxCompanyInfo

    return DidoxCompanyInfo.from_payload(payload)


# ── mapping onto the P7.c DTOs ────────────────────────────────────────────────


def test_lookup_company_maps_the_recorded_record() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient

    client = DidoxGovRegistryClient(_FakeDidox(_info(INFO_FOUND)))
    snapshot = client.lookup_company("310529901")

    assert snapshot.inn == "310529901"
    assert snapshot.name == '"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT'
    assert snapshot.director == "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI"
    assert snapshot.oked == "62090"
    assert snapshot.registered_at == datetime.date(2023, 6, 1)


def test_an_operating_company_is_active_and_keeps_the_registry_wording() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import COMPANY_ACTIVE

    snapshot = DidoxGovRegistryClient(_FakeDidox(_info(INFO_FOUND))).lookup_company("310529901")

    assert snapshot.status == COMPANY_ACTIVE
    assert snapshot.raw_status == "Действующие и имеющие налоговые обязательства"


def test_a_status_we_cannot_read_is_unknown_never_liquidated() -> None:
    """`check_gov_registry` FAILS a case on `liquidated`. Guessing that from an
    unrecognised code would reject a real company on our own ignorance."""
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import COMPANY_UNKNOWN

    payload = {**INFO_FOUND, "statusCode": 77, "statusName": "Нечто новое"}
    snapshot = DidoxGovRegistryClient(_FakeDidox(_info(payload))).lookup_company("310529901")

    assert snapshot.status == COMPANY_UNKNOWN
    assert snapshot.raw_status == "Нечто новое"


def test_a_liquidated_company_is_recognised_by_the_registry_wording() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import COMPANY_LIQUIDATED

    payload = {**INFO_FOUND, "statusCode": 3, "statusName": "Ликвидированные"}
    snapshot = DidoxGovRegistryClient(_FakeDidox(_info(payload))).lookup_company("310529901")

    assert snapshot.status == COMPANY_LIQUIDATED


def test_lookup_vat_reads_the_certificate() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient

    vat = DidoxGovRegistryClient(_FakeDidox(_info(INFO_FOUND))).lookup_vat("310529901")

    assert vat.registered is True
    assert vat.certificate_no == "326080220838"


def test_a_company_without_a_vat_code_is_simply_not_registered() -> None:
    """Not every Uzbek company must be a VAT payer — `check_vat_status` warns
    rather than fails, so the honest answer here is `registered=False`."""
    from app.integrations.didox.registry import DidoxGovRegistryClient

    payload = {**INFO_FOUND, "VATRegCode": None, "VATRegStatus": None}
    vat = DidoxGovRegistryClient(_FakeDidox(_info(payload))).lookup_vat("310529901")

    assert vat.registered is False
    assert vat.certificate_no is None


# ── absence ───────────────────────────────────────────────────────────────────


def test_a_company_the_registry_does_not_know_raises_not_found() -> None:
    from app.integrations.didox.registry import CompanyNotFound, DidoxGovRegistryClient

    client = DidoxGovRegistryClient(_FakeDidox(None))  # the empty-envelope answer

    with pytest.raises(CompanyNotFound):
        client.lookup_company("999999999")
    with pytest.raises(CompanyNotFound):
        client.lookup_vat("999999999")


def test_not_found_is_a_provider_unavailable_so_existing_callers_degrade() -> None:
    """`registry_service.fetch_and_record` catches `ProviderUnavailable` and
    returns None. Inheriting keeps that path — a case gets an `unavailable`
    check and the manual route, not a fabricated verdict."""
    from app.integrations.didox.registry import CompanyNotFound
    from app.integrations.gov_registry import ProviderUnavailable

    assert issubclass(CompanyNotFound, ProviderUnavailable)


def test_licences_are_refused_rather_than_answered_emptily() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import ProviderUnavailable

    client = DidoxGovRegistryClient(_FakeDidox(_info(INFO_FOUND)))

    with pytest.raises(ProviderUnavailable):
        client.lookup_licenses("310529901")


def test_an_outage_stays_an_outage() -> None:
    from app.integrations.didox.client import ProviderUnavailable as DidoxUnavailable
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import ProviderUnavailable

    client = DidoxGovRegistryClient(_FakeDidox(raises=DidoxUnavailable("circuit open")))

    with pytest.raises(ProviderUnavailable):
        client.lookup_company("310529901")


def test_the_empty_envelope_never_becomes_a_snapshot() -> None:
    """Belt and braces on the one mistake that would libel a real company."""
    from app.integrations.didox.client import DidoxCompanyInfo

    assert DidoxCompanyInfo.from_payload(INFO_EMPTY) is None


# ── the protocol and the mode ─────────────────────────────────────────────────


def test_the_didox_client_satisfies_the_registry_protocol() -> None:
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import GovRegistryClient

    assert isinstance(DidoxGovRegistryClient(_FakeDidox()), GovRegistryClient)


def test_the_factory_returns_the_didox_client_on_the_didox_rail(monkeypatch) -> None:  # noqa: ANN001
    from app.integrations import gov_registry
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda db, key: "didox")
    assert isinstance(gov_registry.get_gov_registry_client(None), DidoxGovRegistryClient)


def test_the_registry_mode_still_ships_stub() -> None:
    from app.services.settings_service import _SPECS

    spec = _SPECS["gov_registry_mode"]
    assert spec.default == "stub", "turning the channel on is an operator decision"
    assert "didox" in (spec.choices or ())
