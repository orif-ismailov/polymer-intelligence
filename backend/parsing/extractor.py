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

import anthropic
import instructor
from instructor.core import InstructorRetryException  # noqa: F401 — re-exported for callers

from app.core.config import settings
from app.services import llm_clients

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
#
# `DEFAULT_MODEL` is the value `.env` shipped and is NO LONGER the value used:
# `LLM_EXTRACT_MODEL` is operator-settable, and a module constant captured at
# import cannot follow it. `_live_model()` below is the resolver; this stays
# because `app/tasks/parse.py` imports the name (and its news twin) directly.
#
# `PROMPT_VERSION` is different and stays as-is — `LLM_PROMPT_VERSION` is not
# operator-settable, deliberately: the prompt file it names has to be in the
# image, which makes it a property of the deploy rather than of the operator.
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = settings.LLM_EXTRACT_MODEL
PROMPT_VERSION: str = settings.LLM_PROMPT_VERSION


def _live_model() -> str:
    """The extractor model as configured RIGHT NOW, override included.

    Resolved per call, not bound as a default argument. That distinction is the
    whole bug this replaced: Python evaluates a default at `def` time, so
    `model: str = DEFAULT_MODEL` froze the value at import. The news path passed
    a model explicitly and would have followed a change; this path passes
    nothing and would not — so the admin panel would have switched the model for
    half the pipeline and silently left the other half behind.
    """
    from app.services import (
        settings_service,  # noqa: PLC0415 — lazy: parsing/ must not import app/ at module scope
    )

    return str(settings_service.get("llm_extract_model"))

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

_openai_client = llm_clients.build_openai_structured(settings.OPENAI_API_KEY)
"""The same, for a GPT model — `None` unless `OPENAI_API_KEY` is set.

Which of the two a call uses is decided by the model id, in
`llm_clients.provider_of`. Both are rebound in place by `llm_clients.reset()`
when an operator changes a key.
"""


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------


def extract_signal(
    message_text: str,
    *,
    model: str | None = None,
    prompt_version: str | None = None,
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
        model: Claude model id. None → the live `llm_extract_model` setting
                        (the admin-panel override if one is set, else
                        LLM_EXTRACT_MODEL). Resolved per call — see _live_model.
        prompt_version: Prompt version identifier. None → settings.LLM_PROMPT_VERSION.
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
    # 0. Resolve the defaults HERE rather than in the signature — a default
    #    argument is evaluated once, at import, and would pin the model forever.
    model = model or _live_model()
    prompt_version = prompt_version or PROMPT_VERSION

    # 1. Load versioned prompt — immutable file, never edit existing versions.
    #    Cached by lru_cache in load_prompt so repeated calls have no disk I/O.
    system_prompt = load_prompt(prompt_version)

    # 2. LLM call with instructor validation, in whichever vendor's dialect the
    #    model names (llm_clients.provider_of). create_with_completion returns
    #    (validated_ExtractionResult, raw_Message) so both the structured output
    #    and the token usage are available in one call (AI-SPEC Pitfall 2 — never
    #    use create(), which drops the completion).
    #
    #    The system prompt is cached on the Anthropic path (Claude Haiku 4.5 needs
    #    >=4096 tokens to activate it; extract_v1.md is padded to approach that).
    #    The user message is ONLY the raw channel text — never instructions, which
    #    would be a prompt-injection surface (security_threat_model T-05-10:
    #    data/instruction separation), and never the cache breakpoint (Pitfall 3).
    result, completion, usage, latency_ms = llm_clients.structured(
        _client,
        _openai_client,
        model=model,
        system=system_prompt,
        user=message_text,
        response_model=ExtractionResult,
        max_tokens=512,  # fixed ceiling for a JSON object; unbounded is a cost anti-pattern
    )
    tokens_in = usage.tokens_in
    tokens_out = usage.tokens_out
    cache_read_tokens = usage.cache_read_tokens

    # 3. Build journal row — written to parse_runs by the task orchestrator (05-04).
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
