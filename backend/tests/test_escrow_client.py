"""
The escrow provider contour (P3 W1 — T1.3). No database, no network.

The bank API is promised but not dated, so the *stub rail is a permanent part of
the system*, not a placeholder: an operator confirming movement against a bank
statement is a real mode of operation, and P7 adds a second rail beside it
rather than replacing this one.

What is asserted here is the seam:
  * `EscrowClient` is a Protocol, so `StubEscrowClient` and P7's live client are
    interchangeable without either importing the other;
  * the mode is a RUNTIME setting, so switching rails needs no deploy;
  * choosing `live` today fails loudly (`ProviderUnavailable`) instead of
    silently pretending money moved.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeSettings:
    """Stands in for the app_settings-backed runtime setting."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def get(self, key: str) -> Any:  # noqa: ANN401
        assert key == "escrow_mode"
        return self.mode


class TestRuntimeSetting:
    """`escrow_mode` as an env switch.

    These asserted on `SettingSpec.default`/`.choices` and drove
    `settings_service._coerce` while the switches were rows in `app_settings`.
    The declaration is now the `Settings` field itself, and a bad value is
    refused at STARTUP instead of at a write that no longer exists — so the same
    three properties are checked where they actually live.
    """

    def test_escrow_mode_is_declared_with_a_safe_default(self) -> None:
        from app.core.config import Settings  # noqa: PLC0415

        assert Settings.model_fields["ESCROW_MODE"].get_default() == "stub", (
            "the default must never move real money"
        )

    def test_only_the_two_known_rails_are_accepted(self) -> None:
        """A typo must be refused at startup, not become a silently unroutable
        mode discovered later by a 503."""
        import typing  # noqa: PLC0415

        from app.core.config import Settings  # noqa: PLC0415

        assert typing.get_args(Settings.model_fields["ESCROW_MODE"].annotation) == (
            "stub",
            "live",
        )

    def test_other_string_settings_are_unconstrained(self) -> None:
        """Constraining the mode switches must not also pin the free-text ones
        (the extract model name, the news prompt version)."""
        import typing  # noqa: PLC0415

        from app.core.config import Settings  # noqa: PLC0415

        for env_var in ("LLM_EXTRACT_MODEL", "NEWS_PROMPT_VERSION"):
            field = Settings.model_fields[env_var]
            assert field.annotation is str
            assert typing.get_args(field.annotation) == ()


class TestStubClient:
    def test_satisfies_the_protocol(self) -> None:
        from app.integrations.escrow.client import EscrowClient, StubEscrowClient  # noqa: PLC0415

        client: EscrowClient = StubEscrowClient()
        assert isinstance(client, EscrowClient)

    def test_open_escrow_returns_local_data_only(self) -> None:
        """The stub invents no bank reference: `provider_ref` stays None so a
        `funded` row on the stub rail is never mistaken for a bank-confirmed one."""
        from app.integrations.escrow.client import StubEscrowClient  # noqa: PLC0415

        result = StubEscrowClient().open_escrow(deal_id=7, amount="1000.00", currency="UZS")
        assert result.provider_ref is None
        assert result.mode == "stub"

    def test_status_and_requests_are_no_ops(self) -> None:
        from app.integrations.escrow.client import StubEscrowClient  # noqa: PLC0415

        client = StubEscrowClient()
        assert client.get_status("anything") is None
        # An operator marks movement by hand on this rail; the client must not
        # claim to have asked a bank for anything.
        assert client.request_release("anything") is False
        assert client.request_refund("anything") is False


class TestFactory:
    def test_stub_mode_returns_the_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

        monkeypatch.setattr(escrow_client, "settings_service", _FakeSettings("stub"))
        assert isinstance(escrow_client.get_escrow_client(None), escrow_client.StubEscrowClient)

    def test_live_mode_without_an_adapter_fails_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P7 ships the live client. Until then, selecting `live` must raise —
        falling back to the stub would let an operator believe a bank is
        confirming payments when nothing is."""
        from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

        monkeypatch.setattr(escrow_client, "settings_service", _FakeSettings("live"))
        with pytest.raises(escrow_client.ProviderUnavailable):
            escrow_client.get_escrow_client(None)

    def test_unknown_mode_fails_loudly_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

        monkeypatch.setattr(escrow_client, "settings_service", _FakeSettings("nonsense"))
        with pytest.raises(escrow_client.ProviderUnavailable):
            escrow_client.get_escrow_client(None)

    def test_current_mode_reads_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

        monkeypatch.setattr(escrow_client, "settings_service", _FakeSettings("live"))
        assert escrow_client.current_mode() == "live"
