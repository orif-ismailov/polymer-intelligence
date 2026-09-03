"""
The chemical-registry gateway (P5 W2 — T2.5). No database, no network.

There is no machine-readable state registry of regulated chemistry in Uzbekistan
(INTEGRATIONS.md §4): the law is a draft and НРОХВ is empty. So unlike the escrow
seam — where a real bank API is promised — this stub exists to keep P7 from having
to touch the verdict service later, and it answers "I know nothing" rather than
pretending to be a registry.

That distinction is what the tests below pin: a stub lookup returns None (our own
`substances` table stays the source of truth), and asking for `live` fails loudly
instead of degrading into a silent None that would read like "not regulated".

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

from typing import Any

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


class _FakeSettings:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def get(self, key: str) -> Any:  # noqa: ANN401
        assert key == "chem_registry_mode"
        return self.mode


class TestRuntimeSetting:
    def test_mode_is_declared_with_a_safe_default(self) -> None:
        assert _shipped_default("CHEM_REGISTRY_MODE") == "stub"
        assert _allowed_values("CHEM_REGISTRY_MODE") == ("stub", "live")


class TestStubClient:
    def test_satisfies_the_protocol(self) -> None:
        from app.integrations.chem_registry.client import (  # noqa: PLC0415
            ChemRegistryClient,
            StubChemRegistryClient,
        )

        client: ChemRegistryClient = StubChemRegistryClient()
        assert isinstance(client, ChemRegistryClient)

    def test_lookup_knows_nothing(self) -> None:
        """Returning None is the honest answer: the local registry decides."""
        from app.integrations.chem_registry.client import StubChemRegistryClient  # noqa: PLC0415

        client = StubChemRegistryClient()
        assert client.lookup_substance(hs_code="2914.11") is None
        assert client.lookup_substance(name="ацетон") is None


class TestFactory:
    def test_stub_mode_returns_the_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.chem_registry import client as chem  # noqa: PLC0415

        monkeypatch.setattr(chem, "settings_service", _FakeSettings("stub"))
        assert isinstance(chem.get_chem_registry_client(None), chem.StubChemRegistryClient)

    def test_live_mode_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.chem_registry import client as chem  # noqa: PLC0415

        monkeypatch.setattr(chem, "settings_service", _FakeSettings("live"))
        with pytest.raises(chem.ChemRegistryUnavailable):
            chem.get_chem_registry_client(None)

    def test_unknown_mode_fails_loudly_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.chem_registry import client as chem  # noqa: PLC0415

        monkeypatch.setattr(chem, "settings_service", _FakeSettings("nrohv"))
        with pytest.raises(chem.ChemRegistryUnavailable):
            chem.get_chem_registry_client(None)
