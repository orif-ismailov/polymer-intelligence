"""Registry prefill for the registration wizard (R6 / P7.a — Stage 1).

`GET /portal/companies/lookup` is the endpoint the wizard calls once it knows a
STIR. The behaviour worth pinning is what it does when things are NOT ideal,
because that is what a person filling a form actually meets:

  * no channel configured → 503, and the form stays typeable. A registration
    must never be blocked by a provider we chose to integrate.
  * the registry has no such company → `found=false`, NOT an empty company. The
    provider reports absence as a 200 full of nulls, and passing that through
    would blank a form and put "unknown" on a verification check.
  * a lookup of any STIR → company requisites only. The provider hands us the
    director's ПИНФЛ and tax id; any portal account can call this for any STIR,
    so those must not be in the response.
"""

from __future__ import annotations

import datetime

import pytest

from tests.test_didox_client import INFO_FOUND


def test_the_literal_path_is_declared_above_the_param_route() -> None:
    """Otherwise `/{company_id}` swallows it and "lookup" arrives as a company id
    — the same rule `/directory` lives by."""
    from app.domains.companies.api_portal import router

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    assert "/portal/companies/lookup" in paths
    assert paths.index("/portal/companies/lookup") < paths.index("/portal/companies/{company_id}")


# ── the service gate ──────────────────────────────────────────────────────────


class _Db:
    """Stands in for the session the mode is read from."""


def test_prefill_is_off_unless_an_operator_turned_the_channel_on(monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies import lookup as lookup_service
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda db, key: "stub")

    with pytest.raises(lookup_service.ChannelDisabled) as excinfo:
        lookup_service.lookup_company(_Db(), "310529901")
    assert "didox" in str(excinfo.value)


def test_a_disabled_channel_is_distinguishable_from_an_outage() -> None:
    """The shipped default has no channel, and the form must say NOTHING about
    that — announcing a feature nobody has seen is noise. A configured channel
    that failed is a different event and does earn a line on screen."""
    from app.domains.companies.lookup import ChannelDisabled
    from app.integrations.gov_registry import ProviderUnavailable

    assert issubclass(ChannelDisabled, ProviderUnavailable), "still degrades everywhere else"
    assert ChannelDisabled is not ProviderUnavailable


def test_prefill_refuses_without_a_partner_token(monkeypatch) -> None:  # noqa: ANN001
    """A token-less deployment would spend a request to be told 401."""
    from app.domains.companies import lookup as lookup_service
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda db, key: "didox")
    monkeypatch.setattr(lookup_service, "is_configured", lambda: False)

    with pytest.raises(lookup_service.ChannelDisabled) as excinfo:
        lookup_service.lookup_company(_Db(), "310529901")
    assert "DIDOX_PARTNER_TOKEN" in str(excinfo.value)


def test_prefill_returns_the_record_when_the_channel_is_on(monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies import lookup as lookup_service
    from app.integrations.didox.client import DidoxCompanyInfo
    from app.integrations.didox.registry import DidoxGovRegistryClient
    from app.integrations.gov_registry import client as registry_client

    monkeypatch.setattr(registry_client.settings_service, "get", lambda db, key: "didox")
    monkeypatch.setattr(lookup_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        DidoxGovRegistryClient,
        "fetch_info",
        lambda self, inn: DidoxCompanyInfo.from_payload(INFO_FOUND),
    )

    info = lookup_service.lookup_company(_Db(), "310529901")
    assert info is not None
    assert info.short_name == '"DIDOX TECH" MCHJ'


# ── what the wire carries ─────────────────────────────────────────────────────


def test_the_response_carries_requisites_but_no_personal_identifiers() -> None:
    """Company data is what a counterparty reads off an invoice. A director's
    ПИНФЛ is not, and this endpoint is callable for any STIR by any account."""
    from app.domains.companies.schemas import CompanyRegistryDataOut

    fields = set(CompanyRegistryDataOut.model_fields)

    assert {"legal_name", "legal_address", "bank_mfo", "bank_account", "oked"} <= fields
    assert "director_name" in fields, "a contract names the signatory"
    for leaked in ("director_pinfl", "director_tin", "accountant", "pinfl"):
        assert leaked not in fields


def test_not_found_is_an_answer_not_an_empty_company() -> None:
    from app.domains.companies.schemas import CompanyLookupOut

    out = CompanyLookupOut(found=False)
    assert out.company is None


def test_a_found_company_serializes_the_date_as_a_date() -> None:
    from app.domains.companies.schemas import CompanyRegistryDataOut

    out = CompanyRegistryDataOut(
        tax_id="310529901",
        legal_name='"DIDOX TECH" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
        registration_date=datetime.date(2023, 6, 1),
        registry_status="active",
    )
    assert out.model_dump()["registration_date"] == datetime.date(2023, 6, 1)
