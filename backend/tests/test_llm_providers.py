"""
Running the platform's AI on OpenAI as well as Anthropic.

What is actually risky here is not the plumbing — `instructor` gives both vendors
the same `client.messages.create_with_completion(...)` — it is the three places
they disagree, each of which fails in a different way:

**The request kwargs.** Anthropic takes the system prompt as its own parameter,
OpenAI as the first message; `max_tokens` is `max_completion_tokens`; OpenAI's
reasoning models reject `temperature` outright. All three are 400s, which is the
good case — but a mocked test cannot see a 400, so what is asserted here is the
SHAPE of the kwargs, not the answer.

**The usage fields.** Anthropic's `input_tokens` excludes cache reads, OpenAI's
`prompt_tokens` includes them. Left alone an OpenAI call double-counts its cached
tokens, and `/admin/llm-spend` sums exactly those columns.

**Which client a call reaches.** The four extraction sites now go through one
helper, and ten places in this suite patch `_client` by name expecting to
intercept them. If the helper ever looked the client up itself instead of taking
it from the caller, those ten would silently start making real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import llm_clients, settings_service
from app.services.llm_clients import ANTHROPIC, OPENAI
from tests.conftest import set_switch


def _completion(usage: object) -> MagicMock:
    completion = MagicMock()
    completion.usage = usage
    return completion


class TestTheModelIdNamesTheProvider:
    @pytest.mark.parametrize("model", settings_service.EXTRACT_MODELS)
    def test_every_offered_extract_model_resolves(self, model: str) -> None:
        assert llm_clients.provider_of(model) in {ANTHROPIC, OPENAI}

    @pytest.mark.parametrize("model", settings_service.REPORT_MODELS)
    def test_every_offered_report_model_resolves(self, model: str) -> None:
        assert llm_clients.provider_of(model) in {ANTHROPIC, OPENAI}

    @pytest.mark.parametrize(
        ("model", "provider"),
        [
            ("claude-haiku-4-5", ANTHROPIC),
            ("claude-opus-5", ANTHROPIC),
            ("gpt-4.1-mini", OPENAI),
            ("gpt-5", OPENAI),
            ("o3", OPENAI),
            ("chatgpt-4o-latest", OPENAI),
        ],
    )
    def test_the_families_route_where_they_should(self, model: str, provider: str) -> None:
        assert llm_clients.provider_of(model) == provider

    def test_an_unknown_id_stays_with_anthropic(self) -> None:
        """The safety property of the whole change.

        An operator may pin any model id from `.env`, and before there were two
        providers every one of them went to Anthropic. Routing only on a
        RECOGNISED OpenAI prefix means no deployment can have its provider
        switched underneath it by this feature existing.
        """
        assert llm_clients.provider_of("some-future-claude-thing") == ANTHROPIC
        assert llm_clients.provider_of("") == ANTHROPIC


class TestEachVendorGetsItsOwnDialect:
    def test_anthropic_keeps_the_system_parameter_and_the_cache(self) -> None:
        """`cache_control` is not portable and is not dropped for symmetry — it is
        most of the reason this deployment's LLM bill is what it is."""
        kwargs = llm_clients._request_kwargs(ANTHROPIC, "claude-haiku-4-5", "SYS", "USR", 512)

        assert kwargs["system"] == [
            {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}
        ]
        assert kwargs["messages"] == [{"role": "user", "content": "USR"}]
        assert kwargs["max_tokens"] == 512
        assert kwargs["temperature"] == 0

    def test_openai_takes_the_prompt_as_a_message(self) -> None:
        """OpenAI has no `system` parameter. Passing one is a TypeError at the SDK
        boundary, so the prompt becomes the first message instead."""
        kwargs = llm_clients._request_kwargs(OPENAI, "gpt-4.1-mini", "SYS", "USR", 512)

        assert "system" not in kwargs
        assert kwargs["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "USR"},
        ]

    def test_openai_uses_max_completion_tokens(self) -> None:
        """`max_tokens` is rejected outright by the newer OpenAI models."""
        kwargs = llm_clients._request_kwargs(OPENAI, "gpt-4.1-mini", "SYS", "USR", 512)

        assert kwargs["max_completion_tokens"] == 512
        assert "max_tokens" not in kwargs

    def test_a_non_reasoning_openai_model_still_gets_temperature_zero(self) -> None:
        """Extraction has to be deterministic wherever the vendor allows it."""
        kwargs = llm_clients._request_kwargs(OPENAI, "gpt-4.1", "SYS", "USR", 512)
        assert kwargs["temperature"] == 0

    @pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "o3", "o4-mini"])
    def test_a_reasoning_model_is_sent_no_temperature_at_all(self, model: str) -> None:
        """These accept only the default and answer 400 to anything else — so
        `temperature=0` would not be ignored, it would break every call."""
        assert "temperature" not in llm_clients._request_kwargs(OPENAI, model, "S", "U", 512)


class TestTokenCountsMeanTheSameThingEitherWay:
    def test_anthropic_adds_cache_writes_and_keeps_reads_apart(self) -> None:
        usage = MagicMock(
            input_tokens=100,
            output_tokens=20,
            cache_creation_input_tokens=30,
            cache_read_input_tokens=400,
        )
        result = llm_clients.usage_of(_completion(usage))

        assert (result.tokens_in, result.tokens_out) == (130, 20)
        assert result.cache_read_tokens == 400
        assert result.total == 150  # what the daily budget counts

    def test_openai_cached_tokens_are_subtracted_not_counted_twice(self) -> None:
        """`prompt_tokens` INCLUDES the cached ones. Without the subtraction the
        same tokens land in `tokens_in` and `cache_read_tokens`, and
        `/admin/llm-spend` sums both columns."""
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "prompt_tokens_details"])
        usage.prompt_tokens = 500
        usage.completion_tokens = 20
        usage.prompt_tokens_details = MagicMock(cached_tokens=400)

        result = llm_clients.usage_of(_completion(usage))

        assert (result.tokens_in, result.tokens_out) == (100, 20)
        assert result.cache_read_tokens == 400

    def test_openai_without_a_cache_block_still_reads(self) -> None:
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens = 90
        usage.completion_tokens = 10

        result = llm_clients.usage_of(_completion(usage))

        assert (result.tokens_in, result.tokens_out, result.cache_read_tokens) == (90, 10, 0)

    def test_a_completion_with_no_usage_counts_zero_rather_than_raising(self) -> None:
        """The callers journal whatever comes back here. A missing counter must
        not turn a successful classification into a failed one."""
        assert llm_clients.usage_of(_completion(None)).total == 0


class TestTheCallerStillOwnsTheClient:
    def test_a_claude_model_calls_the_client_the_caller_passed(self) -> None:
        """Ten places in this suite patch `_client` by name. If the helper looked
        the client up itself, all ten would quietly start calling the real API."""
        anthropic_client = MagicMock()
        anthropic_client.messages.create_with_completion.return_value = (
            MagicMock(),
            _completion(MagicMock(input_tokens=1, output_tokens=1)),
        )
        openai_client = MagicMock()

        llm_clients.structured(
            anthropic_client,
            openai_client,
            model="claude-haiku-4-5",
            system="S",
            user="U",
            response_model=MagicMock(),
            max_tokens=64,
        )

        anthropic_client.messages.create_with_completion.assert_called_once()
        openai_client.messages.create_with_completion.assert_not_called()

    def test_a_gpt_model_calls_the_openai_client(self) -> None:
        anthropic_client = MagicMock()
        openai_client = MagicMock()
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens, usage.completion_tokens = 10, 2
        openai_client.messages.create_with_completion.return_value = (
            MagicMock(),
            _completion(usage),
        )

        llm_clients.structured(
            anthropic_client,
            openai_client,
            model="gpt-4.1-mini",
            system="S",
            user="U",
            response_model=MagicMock(),
            max_tokens=64,
        )

        openai_client.messages.create_with_completion.assert_called_once()
        anthropic_client.messages.create_with_completion.assert_not_called()

    def test_a_gpt_model_with_no_openai_client_says_which_thing_is_missing(self) -> None:
        with pytest.raises(llm_clients.NoClient, match="OPENAI_API_KEY"):
            llm_clients.structured(
                MagicMock(),
                None,
                model="gpt-5",
                system="S",
                user="U",
                response_model=MagicMock(),
                max_tokens=64,
            )

    def test_the_report_digest_reads_content_blocks_from_anthropic(self) -> None:
        client = MagicMock()
        block = MagicMock(type="text", text="{}")
        # `spec=` matters: a bare MagicMock auto-creates
        # `cache_creation_input_tokens`, and `4000 + <MagicMock>` is a MagicMock.
        usage = MagicMock(spec=["input_tokens", "output_tokens"])
        usage.input_tokens, usage.output_tokens = 4000, 6500
        client.messages.create.return_value = MagicMock(content=[block], usage=usage)

        answer, usage = llm_clients.text(
            client, None, model="claude-sonnet-4-5", system="S", user="U", max_tokens=99
        )

        assert answer == "{}"
        # The usage is the point of the tuple: the report is the platform's most
        # expensive call and was the only one journalling nothing.
        assert (usage.tokens_in, usage.tokens_out) == (4000, 6500)
        # The raw client takes a plain string, not the cache-block form.
        assert client.messages.create.call_args.kwargs["system"] == "S"

    def test_the_report_digest_reads_choices_from_openai(self) -> None:
        """The one place the two SDKs genuinely stop looking alike."""
        openai_client = MagicMock()
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens, usage.completion_tokens = 4000, 6500
        openai_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=" {} "))], usage=usage
        )

        answer, spent = llm_clients.text(
            MagicMock(), openai_client, model="gpt-4.1", system="S", user="U", max_tokens=99
        )

        assert answer == "{}"
        assert (spent.tokens_in, spent.tokens_out) == (4000, 6500)

    def test_an_empty_openai_answer_is_empty_not_an_exception(self) -> None:
        """`_ai_digest` degrades to the rule-based summary on a falsy answer; an
        IndexError here would take the whole report generation down instead."""
        openai_client = MagicMock()
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens, usage.completion_tokens = 4000, 0
        openai_client.chat.completions.create.return_value = MagicMock(choices=[], usage=usage)

        answer, spent = llm_clients.text(
            MagicMock(), openai_client, model="gpt-4.1", system="S", user="U", max_tokens=9
        )

        assert answer == ""
        # An empty answer was billed like any other — reporting only successful
        # spend would hide exactly the calls worth investigating.
        assert spent.tokens_in == 4000


class TestTheOpenAIKeyIsManagedLikeTheAnthropicOne:
    def test_it_is_sensitive_and_filed_with_the_models(self) -> None:
        spec = settings_service.SPECS["openai_api_key"]
        assert (spec.sensitive, spec.overridable, spec.group) == (True, True, "ai")

    def test_the_env_field_is_optional(self) -> None:
        """Unlike the Anthropic key. A deployment that never selects a GPT model
        must not be made to invent one — the cross-field validator is what asks
        for it, exactly when it is needed."""
        from app.core.config import Settings  # noqa: PLC0415

        assert not Settings.model_fields["OPENAI_API_KEY"].is_required()

    def test_a_rejected_key_never_reaches_the_table(self) -> None:
        db = MagicMock()
        with (
            patch.object(
                llm_clients,
                "verify",
                side_effect=llm_clients.KeyRejected("OpenAI rejected the key"),
            ),
            pytest.raises(settings_service.InvalidSetting, match="OpenAI rejected"),
        ):
            settings_service.set_override(db, "openai_api_key", "sk-wrong", None)
        db.execute.assert_not_called()

    def test_it_is_checked_against_openai_and_not_anthropic(self) -> None:
        db = MagicMock()
        with patch.object(llm_clients, "verify") as verify:
            settings_service.set_override(db, "openai_api_key", "sk-good", None)
        assert verify.call_args.args == ("sk-good", OPENAI)

    def test_the_refusal_carries_openais_reason_and_not_the_key(self) -> None:
        """The body shape here is the one a live 401 actually returned.

        OpenAI's `.body` is ALREADY the inner error (`{"message": …}`) where
        Anthropic's is the envelope (`{"error": {"message": …}}`). Written the
        Anthropic way, this test passed while the real call fell through to the
        SDK's repr — a fixture agreeing with the code and both disagreeing with
        the provider.
        """
        import openai  # noqa: PLC0415

        response = MagicMock(status_code=401, headers={}, request=MagicMock())
        error = openai.AuthenticationError(
            "Error code: 401 - {'error': {'message': 'Incorrect API key provided.'}}",
            response=response,
            body={
                "message": "Incorrect API key provided.",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            },
        )
        with patch("openai.OpenAI") as client:
            client.return_value.models.list.side_effect = error
            with pytest.raises(llm_clients.KeyRejected) as caught:
                llm_clients.verify("sk-a-very-distinctive-wrong-key", OPENAI)

        assert str(caught.value) == "OpenAI rejected the key: Incorrect API key provided."
        assert "sk-a-very-distinctive-wrong-key" not in str(caught.value)

    def test_an_unreachable_provider_refuses_rather_than_storing(self) -> None:
        with patch("openai.OpenAI") as client:
            client.return_value.models.list.side_effect = OSError("connection refused")
            with pytest.raises(llm_clients.KeyRejected, match="Could not reach OpenAI"):
                llm_clients.verify("sk-anything", OPENAI)

    def test_it_is_masked_in_the_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings_service._config, "OPENAI_API_KEY", "sk-proj-supersecret4242")
        db = MagicMock()
        db.execute.return_value.all.return_value = []

        row = {i["key"]: i for i in settings_service.get_all(db)}["openai_api_key"]

        assert "supersecret" not in str(row)
        assert row["value"] == "••••4242"


class TestAGptModelWithoutAKeyIsRefused:
    """The rail that stops the panel offering a model that cannot possibly run.

    Both features degrade rather than error on an LLM failure — the news simply
    classifies badly, the report falls back to a rule-based summary — so without
    this the symptom would be "the AI got worse" with nothing pointing at an
    empty line in `.env`.
    """

    def _settings(self, **overrides: object) -> object:
        from app.core.config import Settings  # noqa: PLC0415

        base = settings_service._config.model_dump()
        base.update(overrides)
        return Settings.model_validate(base)

    def test_boot_fails_when_the_extract_model_is_gpt_with_no_key(self) -> None:
        with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
            self._settings(LLM_EXTRACT_MODEL="gpt-5", OPENAI_API_KEY="")

    def test_boot_fails_when_the_report_model_is_gpt_with_no_key(self) -> None:
        with pytest.raises(ValueError, match="LLM_REPORT_MODEL=gpt-4.1"):
            self._settings(LLM_REPORT_MODEL="gpt-4.1", OPENAI_API_KEY="")

    def test_boot_succeeds_once_the_key_is_there(self) -> None:
        assert self._settings(LLM_EXTRACT_MODEL="gpt-5", OPENAI_API_KEY="sk-x") is not None

    def test_claude_models_never_ask_for_it(self) -> None:
        assert self._settings(LLM_EXTRACT_MODEL="claude-opus-5", OPENAI_API_KEY="") is not None

    def test_the_panel_refuses_the_same_write(self) -> None:
        """No second implementation: `settings_service.validate` builds a
        candidate `Settings`, so the boot check IS the write check."""
        with (
            patch.object(settings_service._config, "OPENAI_API_KEY", ""),
            pytest.raises(settings_service.InvalidSetting, match="OPENAI_API_KEY is required"),
        ):
            settings_service.validate("llm_extract_model", "gpt-5")

    def test_the_refusal_does_not_echo_the_other_credentials(self) -> None:
        """`ValidationError.errors()` embeds `input_value` for every field, and
        the candidate model holds every secret the deployment has."""
        with patch.object(settings_service._config, "OPENAI_API_KEY", ""):
            try:
                settings_service.validate("llm_extract_model", "gpt-5")
            except settings_service.InvalidSetting as exc:
                message = str(exc)
        assert settings_service._config.ANTHROPIC_API_KEY not in message
        assert settings_service._config.JWT_SECRET not in message


class TestBothClientsFollowTheKeys:
    def test_reset_rebinds_both_clients_in_every_imported_module(self) -> None:
        import app.domains.compliance.substance_ai as substance_ai  # noqa: PLC0415
        import app.domains.news.reports as reports  # noqa: PLC0415
        import app.domains.requests.analysis as analysis  # noqa: PLC0415
        import parsing.extractor as extractor  # noqa: PLC0415
        import parsing.news_extractor as news_extractor  # noqa: PLC0415

        modules = [extractor, news_extractor, reports, analysis, substance_ai]
        before = [(m._client, m._openai_client) for m in modules]

        set_switch(anthropic_api_key="sk-ant-rotated", openai_api_key="sk-proj-rotated")
        try:
            llm_clients.reset()
            for module, (old_anthropic, _) in zip(modules, before, strict=True):
                assert module._client is not old_anthropic, module.__name__
                assert module._openai_client is not None, module.__name__
        finally:
            settings_service.clear_snapshot()
            llm_clients.reset()  # restore the originals for the rest of the suite

    def test_reset_leaves_the_openai_client_none_when_there_is_no_key(self) -> None:
        """The common case — every deployment today. `openai.OpenAI(api_key="")`
        raises at CONSTRUCTION, so an unguarded build would make `reset()` fail
        for every module in every process and turn its warning into noise."""
        import parsing.extractor as extractor  # noqa: PLC0415

        set_switch(openai_api_key="")
        try:
            llm_clients.reset()
            assert extractor._openai_client is None
        finally:
            settings_service.clear_snapshot()
            llm_clients.reset()

    def test_the_report_module_gets_raw_clients_not_wrapped_ones(self) -> None:
        """It calls `.messages.create()` / `.chat.completions.create()` and parses
        the JSON itself — an instructor wrapper would change both call shapes."""
        import anthropic  # noqa: PLC0415
        import openai  # noqa: PLC0415

        import app.domains.news.reports as reports  # noqa: PLC0415

        set_switch(openai_api_key="sk-proj-x")
        try:
            llm_clients.reset()
            assert isinstance(reports._client, anthropic.Anthropic)
            assert isinstance(reports._openai_client, openai.OpenAI)
        finally:
            settings_service.clear_snapshot()
            llm_clients.reset()


class TestTheReportModelIsReadThroughTheSettingsService:
    def test_an_override_reaches_the_report(self) -> None:
        """Reading `settings.LLM_REPORT_MODEL` directly would give the panel a
        control that silently does nothing, and stamp `generated_by` with a model
        that did not write the report."""
        import app.domains.news.reports as reports  # noqa: PLC0415

        set_switch(llm_report_model="claude-opus-5")
        assert reports.report_model() == "claude-opus-5"

    def test_it_falls_back_to_env(self) -> None:
        import app.domains.news.reports as reports  # noqa: PLC0415

        assert reports.report_model() == settings_service._config.LLM_REPORT_MODEL
