"""
Tests for parsing.extractor — extract_signal() singleton + journal contract.

All tests mock the instructor client's create_with_completion so NO live LLM call
is made in CI (ANTHROPIC_API_KEY=sk-ant-test-key placeholder is sufficient).

Test coverage:
  1. extract_signal returns (ExtractionResult, journal) with expected keys
  2. The instructor client singleton is not re-created inside extract_signal (reuses module-level object)
  3. extract_signal sets temperature=0 and max_tokens=512 in the call kwargs (Pitfall 4)
  4. extract_signal does NOT catch InstructorRetryException — it propagates to caller
  5. The module-level client is patched once (not per call)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ExtractionResult is the response_model used by extractor
from parsing.schemas import ExtractionResult, SignalKind


def _make_extraction_result() -> ExtractionResult:
    """Return a valid ExtractionResult for test patching."""
    return ExtractionResult(
        is_relevant=True,
        kind=SignalKind.SELL_OFFER,
        product="PP",
        grade_text="T30S",
        volume=Decimal("50"),
        volume_unit="MT",
        price=Decimal("950"),
        currency="USD",
        region=None,
        counterparty_text=None,
        urgency=None,
        lead_score=None,
        confidence=0.9,
    )


def _make_fake_completion(input_tokens: int = 120, output_tokens: int = 40) -> MagicMock:
    """Return a fake anthropic Message completion object."""
    completion = MagicMock()
    completion.usage.input_tokens = input_tokens
    completion.usage.output_tokens = output_tokens
    # cache_creation_input_tokens and cache_read_input_tokens are optional attributes
    # getattr with default=0 is used in extractor.py, so simulate them missing
    del completion.usage.cache_creation_input_tokens
    del completion.usage.cache_read_input_tokens
    completion.model_dump.return_value = {"id": "fake-msg", "type": "message", "usage": {}}
    return completion


class TestExtractSignalJournal:
    """Test 1: extract_signal returns (ExtractionResult, journal) with required keys."""

    def test_journal_keys_and_values(self) -> None:
        """extract_signal returns a journal dict with all required keys populated."""
        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion(input_tokens=120, output_tokens=40)

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )
            from parsing.extractor import PARSER_NATIVE, PARSER_TOOLS, extract_signal

            result, journal = extract_signal("Продам ПП T30S 50 тонн по 950 у.е.")

        # result must be ExtractionResult
        assert isinstance(result, ExtractionResult)
        assert result.is_relevant is True
        assert result.product == "PP"

        # journal must have all required keys
        required_keys = {
            "parser",
            "model",
            "prompt_version",
            "tokens_in",
            "tokens_out",
            "latency_ms",
            "raw_response",
        }
        assert required_keys.issubset(set(journal.keys())), (
            f"Missing journal keys: {required_keys - set(journal.keys())}"
        )

        # parser must be one of the defined constants
        assert journal["parser"] in {PARSER_TOOLS, PARSER_NATIVE}

        # tokens_in must be >= input_tokens (may include cache_creation tokens)
        assert journal["tokens_in"] >= 120

        # tokens_out must be the actual output tokens
        assert journal["tokens_out"] == 40

        # latency_ms must be a non-negative number
        assert journal["latency_ms"] >= 0

        # raw_response must be present (the completion.model_dump() output)
        assert journal["raw_response"] is not None


class TestClientSingleton:
    """Test 2: The module-level client singleton is not re-created inside extract_signal."""

    def test_client_reused_across_calls(self) -> None:
        """Two calls to extract_signal reuse the same module-level _client object."""
        import parsing.extractor as extractor_module

        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion()

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )

            # First call
            extractor_module.extract_signal("msg 1")
            # Second call
            extractor_module.extract_signal("msg 2")

            # The same mock was called twice — the client was not replaced
            assert mock_client.messages.create_with_completion.call_count == 2

    def test_singleton_defined_at_module_level(self) -> None:
        """_client is defined as a module-level attribute (not inside extract_signal)."""
        import parsing.extractor as extractor_module

        # The attribute must exist on the module object before any call
        assert hasattr(extractor_module, "_client"), (
            "_client must be a module-level attribute, not created inside extract_signal"
        )


class TestExtractSignalCallKwargs:
    """Test 3: extract_signal passes temperature=0 and max_tokens=512 (Pitfall 4)."""

    def test_temperature_zero_and_max_tokens(self) -> None:
        """The LLM call must have temperature=0 and max_tokens=512 explicitly set."""
        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion()

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )
            from parsing.extractor import extract_signal

            extract_signal("Продам PP 100 тонн $900")

        call_kwargs = mock_client.messages.create_with_completion.call_args
        # call_args is a Call object; kwargs are the keyword arguments
        kwargs: dict[str, Any] = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]

        assert kwargs.get("temperature") == 0, (
            f"temperature must be explicitly 0, got {kwargs.get('temperature')!r}"
        )
        assert kwargs.get("max_tokens") == 512, (
            f"max_tokens must be 512, got {kwargs.get('max_tokens')!r}"
        )

    def test_max_retries_two(self) -> None:
        """extract_signal passes max_retries=2 to instructor."""
        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion()

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )
            from parsing.extractor import extract_signal

            extract_signal("Test message")

        call_kwargs = mock_client.messages.create_with_completion.call_args
        kwargs: dict[str, Any] = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        assert kwargs.get("max_retries") == 2

    def test_system_block_has_cache_control_ephemeral(self) -> None:
        """The system block must have cache_control ephemeral (Pitfall 3)."""
        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion()

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )
            from parsing.extractor import extract_signal

            extract_signal("Test message")

        call_kwargs = mock_client.messages.create_with_completion.call_args
        kwargs: dict[str, Any] = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]

        system = kwargs.get("system", [])
        assert isinstance(system, list) and len(system) > 0, "system block must be a non-empty list"
        first_block = system[0]
        assert "cache_control" in first_block, (
            "system block must contain cache_control for prompt caching (Pitfall 3)"
        )
        assert first_block["cache_control"].get("type") == "ephemeral", (
            "cache_control type must be 'ephemeral'"
        )

    def test_response_model_is_extraction_result(self) -> None:
        """extract_signal passes response_model=ExtractionResult."""
        fake_result = _make_extraction_result()
        fake_completion = _make_fake_completion()

        with patch("parsing.extractor._client") as mock_client:
            mock_client.messages.create_with_completion.return_value = (
                fake_result,
                fake_completion,
            )
            from parsing.extractor import extract_signal

            extract_signal("Test")

        call_kwargs = mock_client.messages.create_with_completion.call_args
        kwargs: dict[str, Any] = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        assert kwargs.get("response_model") is ExtractionResult


class TestInstructorRetryExceptionPropagates:
    """Test 4: extract_signal does NOT swallow InstructorRetryException (Pitfall 5/6)."""

    def test_instructor_retry_exception_propagates(self) -> None:
        """InstructorRetryException raised by create_with_completion must propagate."""
        from instructor.core import InstructorRetryException

        with patch("parsing.extractor._client") as mock_client:
            # Simulate instructor exhausting all retries (instructor 1.15.3 signature)
            mock_client.messages.create_with_completion.side_effect = (
                InstructorRetryException(
                    "All retries failed",
                    n_attempts=2,
                    total_usage=120,
                )
            )

            from parsing.extractor import extract_signal

            with pytest.raises(InstructorRetryException):
                extract_signal("Any message")
