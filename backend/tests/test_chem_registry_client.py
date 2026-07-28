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


class _FakeSettings:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def get(self, _db: Any, key: str) -> Any:  # noqa: ANN401
        assert key == "chem_registry_mode"
        return self.mode


class TestRuntimeSetting:
    def test_mode_is_declared_with_a_safe_default(self) -> None:
        from app.services.settings_service import _SPECS  # noqa: PLC0415

        spec = _SPECS.get("chem_registry_mode")
        assert spec is not None
        assert spec.default == "stub"
        assert spec.choices == ("stub", "live")


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
