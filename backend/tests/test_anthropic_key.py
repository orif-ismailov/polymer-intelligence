"""
Rotating the Anthropic API key from the admin panel.

Three properties, and each guards a way this could go quietly wrong.

**The clients must follow the key.** Five modules build an Anthropic client at
import with the key baked in. If they did not follow a change, an operator would
paste a working key, the panel would say it was saved, and every LLM feature
would go on failing with the old one until somebody restarted the workers — the
provider looking broken while the configuration looked right.

**A bad key must not be stored.** This one credential drives news
classification, the daily reports, buyer-request analysis and the substance
hint, and every one of them DEGRADES on an LLM failure rather than erroring. A
typo would therefore be expensive and silent.

**The key must not leak.** It is Fernet-encrypted at rest, masked on read, and
admin-only to write — machinery this setting inherits rather than adds, so what
is tested here is that it is actually wired to it.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import llm_clients, settings_service
from tests.conftest import set_switch


class TestTheSpecIsWiredToTheSecretMachinery:
    def test_the_key_is_sensitive(self) -> None:
        """`sensitive` is what buys Fernet-at-rest, masking and the admin-only
        write. A plain overridable spec would store the key as readable JSONB."""
        spec = settings_service.SPECS["anthropic_api_key"]
        assert spec.sensitive is True
        assert spec.overridable is True

    def test_it_is_filed_with_the_model_not_with_news(self) -> None:
        """The key and the model drive four features between them; filing either
        under `news` would misdescribe what changing them affects."""
        assert settings_service.SPECS["anthropic_api_key"].group == "ai"
        assert settings_service.SPECS["llm_extract_model"].group == "ai"

    def test_the_env_field_is_still_required(self) -> None:
        """The override is a layer on top, not a replacement. `Settings` keeps no
        default, so a deployment with no key anywhere still fails at startup
        rather than at the first article."""
        from app.core.config import Settings  # noqa: PLC0415

        assert Settings.model_fields["ANTHROPIC_API_KEY"].is_required()

    def test_it_is_masked_in_the_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings_service._config, "ANTHROPIC_API_KEY", "sk-ant-supersecret9999")
        db = MagicMock()
        db.execute.return_value.all.return_value = []
        row = {i["key"]: i for i in settings_service.get_all(db)}["anthropic_api_key"]
        assert "supersecret" not in str(row)
        assert row["value"] == "••••9999"


class TestAKeyIsCheckedBeforeItIsStored:
    def test_a_rejected_key_never_reaches_the_table(self) -> None:
        """The refusal happens in `set_override`, before the INSERT — so the key
        in use keeps working and there is nothing to roll back."""
        db = MagicMock()
        with (
            patch.object(
                llm_clients,
                "verify",
                side_effect=llm_clients.KeyRejected("Anthropic rejected the key"),
            ),
            pytest.raises(settings_service.InvalidSetting, match="Anthropic rejected"),
        ):
            settings_service.set_override(db, "anthropic_api_key", "sk-ant-wrong", None)
        db.execute.assert_not_called()

    def test_an_accepted_key_is_stored_encrypted(self) -> None:
        """Ciphertext is what makes this table safe to hold the key: a backup, a
        replica or a `SELECT *` must not expose it."""
        from app.core.crypto import decrypt_pii  # noqa: PLC0415

        db = MagicMock()
        with patch.object(llm_clients, "verify", return_value=None):
            settings_service.set_override(db, "anthropic_api_key", "sk-ant-good", None)

        statement = db.execute.call_args.args[0]
        stored = statement.compile().params["value"]
        assert "sk-ant-good" not in str(stored)
        assert decrypt_pii(str(stored).encode("utf-8")) == "sk-ant-good"

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(llm_clients.KeyRejected, match="cannot be empty"):
            llm_clients.verify("   ")

    def test_no_other_setting_is_probed(self) -> None:
        """One credential, one reason. The Didox token is validated by the rail
        that needs it and its provider has a lockout ladder that punishes
        probing; the escrow secret is checked by a bank we cannot call."""
        db = MagicMock()
        with patch.object(llm_clients, "verify") as verify:
            settings_service.set_override(db, "news_refresh_interval_minutes", 30, None)
        verify.assert_not_called()

    def test_the_refusal_carries_the_providers_reason_and_not_the_key(self) -> None:
        """The operator needs to know WHY it was refused, and nothing about the
        string they just pasted."""
        import anthropic  # noqa: PLC0415

        response = MagicMock(status_code=401, headers={}, request=MagicMock())
        error = anthropic.AuthenticationError("API key is invalid.", response=response, body=None)
        with patch("anthropic.Anthropic") as client:
            client.return_value.models.list.side_effect = error
            with pytest.raises(llm_clients.KeyRejected) as caught:
                llm_clients.verify("sk-ant-a-very-distinctive-wrong-key")

        assert "sk-ant-a-very-distinctive-wrong-key" not in str(caught.value)
        assert "invalid" in str(caught.value).lower()

    def test_the_reason_is_the_sentence_and_not_the_envelope(self) -> None:
        """A real 401 arrives as `Error code: 401 - {'type': 'error', 'error':
        {...}}` — a Python repr in a red banner. The sentence inside it is the
        part an operator can act on, so that is what is shown."""
        import anthropic  # noqa: PLC0415

        response = MagicMock(status_code=401, headers={}, request=MagicMock())
        error = anthropic.AuthenticationError(
            "Error code: 401 - {'type': 'error', 'error': {'message': 'API key is invalid.'}}",
            response=response,
            body={
                "type": "error",
                "error": {"type": "authentication_error", "message": "API key is invalid."},
            },
        )
        with patch("anthropic.Anthropic") as client:
            client.return_value.models.list.side_effect = error
            with pytest.raises(llm_clients.KeyRejected) as caught:
                llm_clients.verify("sk-ant-wrong")

        assert str(caught.value) == "Anthropic rejected the key: API key is invalid."

    def test_an_unreachable_provider_refuses_rather_than_storing(self) -> None:
        """The deliberate trade: an outage blocks a rotation, which is a wait.
        Storing an unverified key would be an outage of our own."""
        with patch("anthropic.Anthropic") as client:
            client.return_value.models.list.side_effect = OSError("connection refused")
            with pytest.raises(llm_clients.KeyRejected, match="Could not reach Anthropic"):
                llm_clients.verify("sk-ant-anything")


class TestTheClientsFollowTheKey:
    def test_reset_rebinds_every_imported_client(self) -> None:
        """The whole point. Five modules hold a client built at import; after a
        key change each must be holding a client built with the new one."""
        import app.domains.compliance.substance_ai as substance_ai  # noqa: PLC0415
        import app.domains.news.reports as reports  # noqa: PLC0415
        import app.domains.requests.analysis as analysis  # noqa: PLC0415
        import parsing.extractor as extractor  # noqa: PLC0415
        import parsing.news_extractor as news_extractor  # noqa: PLC0415

        modules = [extractor, news_extractor, reports, analysis, substance_ai]
        before = [m._client for m in modules]

        set_switch(anthropic_api_key="sk-ant-rotated-key")
        try:
            llm_clients.reset()
            assert all(m._client is not old for m, old in zip(modules, before, strict=True))
        finally:
            settings_service.clear_snapshot()
            llm_clients.reset()  # put the originals' key back for the rest of the suite

    def test_reports_keeps_its_raw_client(self) -> None:
        """`reports` is the odd one out — a raw `anthropic.Anthropic` calling
        `.messages.create()`, where the other four are instructor-wrapped and
        call `.create_with_completion()`. Rebinding must not swap its type."""
        import anthropic  # noqa: PLC0415

        import app.domains.news.reports as reports  # noqa: PLC0415

        llm_clients.reset()
        assert isinstance(reports._client, anthropic.Anthropic)

    def test_the_client_stays_a_module_attribute(self) -> None:
        """A lazy factory would have been tidier and would have broken the
        twenty-four places the suite patches these clients by name. Rebinding
        keeps that contract, and this is the assertion that keeps it kept."""
        import app.domains.compliance.substance_ai as substance_ai  # noqa: PLC0415
        import app.domains.news.reports as reports  # noqa: PLC0415
        import app.domains.requests.analysis as analysis  # noqa: PLC0415
        import parsing.extractor as extractor  # noqa: PLC0415
        import parsing.news_extractor as news_extractor  # noqa: PLC0415

        for module in (extractor, news_extractor, reports, analysis, substance_ai):
            assert hasattr(module, "_client"), module.__name__

    def test_reset_never_raises_on_a_bad_module(self) -> None:
        """A failure to rebuild must not block the write that triggered it, or an
        operator correcting a key would be blocked by the thing they are fixing."""
        with patch.object(llm_clients, "_rebind", side_effect=RuntimeError("boom")):
            llm_clients.reset()  # must not raise

    def test_the_live_key_prefers_the_override(self) -> None:
        set_switch(anthropic_api_key="sk-ant-from-the-panel")
        assert llm_clients.live_key() == "sk-ant-from-the-panel"
        settings_service.clear_snapshot()
        assert llm_clients.live_key() == settings_service._config.ANTHROPIC_API_KEY
