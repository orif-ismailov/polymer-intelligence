"""Gov-registry gateway contract (R6 / P7.c — T4.2).

There is no realtime API for private companies without ПЦД access, and that
access process is not normatively formalised (INTEGRATIONS.md §3). So this
gateway ships as an interface plus a stub, and the tests are about honesty:

  * the stub **raises `ProviderUnavailable`** from every lookup. It does not
    return an empty snapshot. An empty answer is indistinguishable from "the
    registry has no record of this company", which would turn a missing
    integration into a verification finding about a real business.
  * `live` also raises, with a message naming what is missing, rather than
    quietly falling back to the stub. A stub standing in for a state registry is
    the one thing this seam must never do.
  * the DTOs round-trip through the JSONB payload, because the snapshot row is
    the ONLY thing the check functions read — a lossy payload would silently
    downgrade a check.
"""

from __future__ import annotations

import datetime

import pytest


def _shipped_default(env_var: str) -> object:
    """The value a deployment runs on when `.env` says nothing.

    Reads `Settings` rather than a `SettingSpec`: since the switches moved into
    the env contract the field IS the declaration, so asserting anywhere else
    would be testing a copy.
    """
    from app.core.config import Settings  # noqa: PLC0415

    return Settings.model_fields[env_var].get_default()


def _allowed_values(env_var: str) -> tuple[object, ...]:
    """The closed set a mode switch accepts, off its `Literal` annotation."""
    import typing  # noqa: PLC0415

    from app.core.config import Settings  # noqa: PLC0415

    return typing.get_args(Settings.model_fields[env_var].annotation)

# ── DTOs and their payload round-trip ─────────────────────────────────────────


def test_company_snapshot_round_trips_through_the_payload() -> None:
    from app.integrations.gov_registry import CompanySnapshot, company_from_payload

    snapshot = CompanySnapshot(
        inn="301234567",
        name='ООО "ПОЛИМЕР ТРЕЙД"',
        status="active",
        raw_status="ДЕЙСТВУЮЩЕЕ",
        director="Иванов И.И.",
        oked="20160",
        address="г. Ташкент, ул. Навои 1",
        registered_at=datetime.date(2019, 4, 12),
    )

    assert company_from_payload(snapshot.as_payload()) == snapshot


def test_a_company_snapshot_needs_only_the_inn() -> None:
    """A registry that answers "exists, nothing else" is still a usable answer."""
    from app.integrations.gov_registry import CompanySnapshot, company_from_payload

    snapshot = CompanySnapshot(inn="301234567")
    restored = company_from_payload(snapshot.as_payload())

    assert restored == snapshot
    assert restored.status == "unknown", "an unstated status is unknown, not active"


def test_vat_snapshot_round_trips() -> None:
    from app.integrations.gov_registry import VatSnapshot, vat_from_payload

    snapshot = VatSnapshot(
        registered=True,
        certificate_no="3012345670001",
        valid_from=datetime.date(2021, 1, 1),
        raw_status="Действующее свидетельство",
    )
    assert vat_from_payload(snapshot.as_payload()) == snapshot


def test_licenses_round_trip_as_a_list() -> None:
    from app.integrations.gov_registry import (
        LicenseSnapshot,
        licenses_from_payload,
        licenses_payload,
    )

    items = [
        LicenseSnapshot(
            regime="precursor_list_iv",
            number="AA-0001",
            issuer="Минздрав",
            issued_at=datetime.date(2025, 3, 1),
            expires_at=datetime.date(2027, 3, 1),
            status="active",
        ),
        LicenseSnapshot(regime="explosive_toxic", number="BB-0002"),
    ]
    assert licenses_from_payload(licenses_payload(items)) == items


def test_an_unparseable_date_in_a_payload_does_not_explode() -> None:
    """Payloads are read back from JSONB written by earlier code and by operators."""
    from app.integrations.gov_registry import company_from_payload

    snapshot = company_from_payload({"inn": "301234567", "registered_at": "not-a-date"})
    assert snapshot.registered_at is None


# ── the stub ──────────────────────────────────────────────────────────────────


def test_the_stub_refuses_rather_than_answering_emptily() -> None:
    """An empty snapshot would read as "no such company" — a finding about a real
    business, caused by us not having an integration."""
    from app.integrations.gov_registry import ProviderUnavailable, StubGovRegistryClient

    stub = StubGovRegistryClient()
    for call in (stub.lookup_company, stub.lookup_licenses, stub.lookup_vat):
        with pytest.raises(ProviderUnavailable):
            call("301234567")


def test_the_stub_satisfies_the_protocol() -> None:
    from app.integrations.gov_registry import GovRegistryClient, StubGovRegistryClient

    assert isinstance(StubGovRegistryClient(), GovRegistryClient)


# ── the factory ───────────────────────────────────────────────────────────────


class _Settings:
    """Minimal stand-in for the settings service the factory reads."""

    def __init__(self, mode: str) -> None:
        self.mode = mode


def test_the_factory_returns_the_stub_on_the_stub_rail(monkeypatch) -> None:  # noqa: ANN001
    from app.integrations import gov_registry
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda key: "stub")
    assert isinstance(gov_registry.get_gov_registry_client(None), gov_registry.StubGovRegistryClient)


def test_the_factory_refuses_live_because_there_is_no_adapter(monkeypatch) -> None:  # noqa: ANN001
    """Loud 503 over a silent stub: an operator must never believe a state
    registry confirmed something when nothing did."""
    from app.integrations import gov_registry
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda key: "live")
    with pytest.raises(gov_registry.ProviderUnavailable) as excinfo:
        gov_registry.get_gov_registry_client(None)
    assert "adapter" in str(excinfo.value)


def test_the_factory_refuses_a_mode_it_does_not_know(monkeypatch) -> None:  # noqa: ANN001
    from app.integrations import gov_registry
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda key: "pcd")
    with pytest.raises(gov_registry.ProviderUnavailable):
        gov_registry.get_gov_registry_client(None)


# ── the runtime setting ───────────────────────────────────────────────────────


def test_the_mode_is_a_runtime_setting_shipping_stub() -> None:
    assert _shipped_default("GOV_REGISTRY_MODE") == "stub"
    # P7.a added the `didox` rail alongside these two; the default is unchanged.
    assert _allowed_values("GOV_REGISTRY_MODE") == ("stub", "didox", "live")
