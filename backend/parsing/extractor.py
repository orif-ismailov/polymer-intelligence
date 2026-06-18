"""
Phase 5 LLM extraction service — instructor + Anthropic SDK.

Transport spike result (AI-SPEC §4 "Transport spike — pin one approach early"):
  Both Mode.TOOLS (instructor) and Mode.JSON were evaluated against the AI-SPEC
  recommendation. instructor Mode.TOOLS is pinned as the default because:
  - Claude native tool-use forces structured output (high schema adherence)
  - instructor's reask loop handles ValidationError automatically (max_retries=2)
  - create_with_completion returns (result, completion) in one call, giving token
    usage for journaling without a second round-trip (AI-SPEC Pitfall 2)
  To switch to native tool-use (Mode.JSON or a raw anthropic client), update PARSER
  to PARSER_NATIVE and replace _client with a non-instructor anthropic client. This
  is the ONLY place that changes — the rest of the pipeline reads journal['parser']
  to distinguish the two paths in parse_runs.parser.

  The live spike comparison against dev_golden_20 runs in 05-05; if the winner
  changes after that spike, flip PARSER and re-pin here.

Module-level singleton (AI-SPEC Pitfall 1):
  _raw_client and _client are constructed ONCE at import time. They are safe for
  Celery prefork workers because the instructor-wrapped client holds no persistent
  connection state — it constructs an httpx client per call internally.

  The client construction reads ANTHROPIC_API_KEY from settings at import time.
  Under CI (ANTHROPIC_API_KEY=sk-ant-test-key placeholder), this creates a client
  object but makes no network call — network I/O only happens when
  _client.messages.create_with_completion() is called. Tests patch
  parsing.extractor._client so no network call ever occurs in CI.

InstructorRetryException:
  extract_signal deliberately does NOT catch InstructorRetryException (AI-SPEC Pitfall 5/6).
  When instructor exhausts all retries (max_retries=2), the exception propagates to the
  caller (05-04 task orchestrator), which owns the dead-letter decision:
    - write parse_runs.status = 'error'
    - capture raw_response
    - enqueue for human review
    - never emit a partial/invented signal

Usage:
    from parsing.extractor import extract_signal

    try:
        result, journal = extract_signal(message_text)
    except BudgetExceeded:
        result = rule_based_extract(message_text)  # degrade gracefully
        # ... enqueue for nightly catch-up
    except InstructorRetryException:
        # ... dead-letter: write parse_run error, enqueue needs_review

Raises:
    BudgetExceeded — caller must fall back to rule-based extraction
    InstructorRetryException — all retries failed; caller must dead-letter
"""

from __future__ import annotations

import time

import anthropic
import instructor
from instructor.core import InstructorRetryException  # noqa: F401 — re-exported for callers

from app.core.config import settings

from .prompts.loader import load_prompt
from .schemas import BudgetExceeded, ExtractionResult  # noqa: F401 — re-exported

# ---------------------------------------------------------------------------
# Transport constants — the parser value is stamped into parse_runs.parser
# so the extraction path is always attributable.
# ---------------------------------------------------------------------------

PARSER_TOOLS = "llm_extract_tools"
"""Mode.TOOLS path via instructor.from_anthropic — current spike default."""

PARSER_NATIVE = "llm_extract_native"
"""Native Claude tool-use path (no instructor wrapper) — defined for future spike."""

# Pinned to TOOLS transport after the AI-SPEC §4 spike analysis.
# To switch: set PARSER = PARSER_NATIVE and replace _client with a raw anthropic client.
PARSER = PARSER_TOOLS

# ---------------------------------------------------------------------------
# Default model and prompt version — read from settings so deploy config
# controls the live model without code changes.
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = settings.LLM_EXTRACT_MODEL
PROMPT_VERSION: str = settings.LLM_PROMPT_VERSION

# ---------------------------------------------------------------------------
# Module-level singleton (AI-SPEC Pitfall 1 — patch ONCE, reuse across tasks)
# ---------------------------------------------------------------------------

_raw_client: anthropic.Anthropic = anthropic.Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
)
"""Raw Anthropic client — constructed once at module import, patched in tests."""

_client: instructor.Instructor = instructor.from_anthropic(
    _raw_client,
    mode=instructor.Mode.TOOLS,
)
"""instructor-patched client — use for create_with_completion calls."""


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------


def extract_signal(
    message_text: str,
    *,
    model: str = DEFAULT_MODEL,
    prompt_version: str = PROMPT_VERSION,
) -> tuple[ExtractionResult, dict]:
    """Classify and extract a polymer market signal from a Telegram message.

    Calls the LLM exactly ONCE per message. The instructor wrapper handles
    validation and re-asks (up to max_retries=2) internally.

    Security (T-05-10):
        Channel text is placed ONLY in the user turn (messages list). The system
        prompt (static, cached) declares user content as data, not instructions.
        Mode.TOOLS constrains output to the ExtractionResult tool schema — injected
        "ignore instructions" text cannot change the output shape.

    Security (T-05-13):
        ANTHROPIC_API_KEY is read only from settings and never logged. The raw_response
        stored in journal is the completion object (no key material).

    Args:
        message_text: Raw Telegram message text. MUST be pre-processed via
                      prepare_message_text() so blank messages are skipped
                      and oversized forwards are truncated (G6 guard).
        model: Claude model id. Defaults to settings.LLM_EXTRACT_MODEL.
        prompt_version: Prompt version identifier. Defaults to settings.LLM_PROMPT_VERSION.
                        Stored verbatim in parse_runs.prompt_version for replay.

    Returns:
        tuple[ExtractionResult, dict]: The validated extraction result and a journal
            dict with keys: parser, model, prompt_version, tokens_in, tokens_out,
            cache_read_tokens, latency_ms, raw_response.
            Write journal to parse_runs for audit trail and eval replay (AI-SPEC FM#5).

    Raises:
        BudgetExceeded: Daily token budget exhausted. Caller must fall back to
                        rule_based_extract() and enqueue for nightly catch-up (G4).
        InstructorRetryException: instructor exhausted max_retries (default 2).
                        Caller must dead-letter: set parse_runs.status='error',
                        capture raw response, enqueue for human review (G3).
                        DO NOT catch this here — the orchestrator (05-04) owns the
                        dead-letter decision (AI-SPEC Pitfall 5/6).
    """
    # 1. Load versioned prompt — immutable file, never edit existing versions.
    #    Cached by lru_cache in load_prompt so repeated calls have no disk I/O.
    system_prompt = load_prompt(prompt_version)

    # 2. LLM call with instructor validation.
    #    create_with_completion returns (validated_ExtractionResult, raw_Message)
    #    so both the structured output and the token usage are available in one call
    #    (AI-SPEC Pitfall 2 — never use create() which drops the completion).
    t0 = time.monotonic()
    result, completion = _client.messages.create_with_completion(
        model=model,
        max_tokens=512,         # fixed ceiling for a JSON object; unbounded is a cost anti-pattern
        temperature=0,          # extraction must be deterministic (AI-SPEC Pitfall 4)
        system=[
            {
                "type": "text",
                "text": system_prompt,
                # Cache the static system prompt.
                # Claude Haiku 4.5 requires >=4096 tokens to activate; the extract_v1.md
                # prompt is padded to approach that threshold (05-01 SUMMARY confirms 277 lines).
                # NEVER put cache_control on the user message (AI-SPEC Pitfall 3).
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                # User message is ONLY the raw channel text — no instructions appended.
                # Mixing instructions into the user turn is a prompt-injection surface
                # (security_threat_model T-05-10: data/instruction separation).
                "content": message_text,
            }
        ],
        response_model=ExtractionResult,
        max_retries=2,          # instructor retries on pydantic.ValidationError
    )
    latency_ms = (time.monotonic() - t0) * 1000.0

    # 3. Surface token usage for journaling.
    #    cache_creation_input_tokens and cache_read_input_tokens may not exist on
    #    older API versions or in mocked tests — use getattr with default 0.
    usage = completion.usage
    tokens_in = usage.input_tokens + getattr(usage, "cache_creation_input_tokens", 0)
    tokens_out = usage.output_tokens
    cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0)

    # 4. Build journal row — written to parse_runs by the task orchestrator (05-04).
    #    Every field is required for audit trail and eval replay (AI-SPEC FM#5).
    journal: dict = {
        "parser": PARSER,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_tokens": cache_read_tokens,
        "latency_ms": latency_ms,
        "raw_response": completion.model_dump(),  # full completion stored for replay
    }

    return result, journal
