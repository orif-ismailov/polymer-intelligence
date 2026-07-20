"""
News-Intelligence LLM extractor (Phase 7b) — instructor + Anthropic SDK.

Mirrors parsing.extractor but produces a NewsArticle (news classification) instead of
an ExtractionResult (trade signal). Same guarantees: instructor Mode.TOOLS forced
structured output, a static cached system prompt, temperature 0, and a journal dict for
parse_runs. Clients are module-level singletons built at import; tests patch
parsing.news_extractor._client so no network call happens in CI.

Prompts are versioned + immutable: parsing/prompts/news_extract_vN.md. To change a
prompt, add news_extract_v{N+1}.md and bump NEWS_PROMPT_VERSION.
"""

from __future__ import annotations

import functools
import time
from pathlib import Path

import anthropic
import instructor
from instructor.core import InstructorRetryException  # noqa: F401 — re-exported for callers

from app.core.config import settings
from parsing.news_schemas import NewsArticle

NEWS_PARSER = "news_extract_tools"
NEWS_PROMPT_VERSION = "v2"
DEFAULT_MODEL: str = settings.LLM_EXTRACT_MODEL
# v2 emits analysis + recommendation + ru/uz/en translations, so the completion is
# larger than the v1 classification-only output.
NEWS_MAX_TOKENS = 3500

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@functools.lru_cache(maxsize=4)
def load_news_prompt(version: str) -> str:
    path = _PROMPTS_DIR / f"news_extract_{version}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


_raw_client: anthropic.Anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
_client: instructor.Instructor = instructor.from_anthropic(_raw_client, mode=instructor.Mode.TOOLS)


def extract_news(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    prompt_version: str = NEWS_PROMPT_VERSION,
) -> tuple[NewsArticle, dict]:
    """Classify one news item into a NewsArticle. Calls the LLM exactly once.

    The static system prompt is cached; the news item text goes ONLY in the user turn
    (data/instruction separation). Returns (NewsArticle, journal) — write the journal
    to parse_runs for audit/replay.

    Raises:
        InstructorRetryException: instructor exhausted its retries — caller dead-letters.
    """
    system_prompt = load_news_prompt(prompt_version)

    t0 = time.monotonic()
    result, completion = _client.messages.create_with_completion(
        model=model,
        max_tokens=NEWS_MAX_TOKENS,
        temperature=0,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}],
        response_model=NewsArticle,
        max_retries=2,
    )
    latency_ms = (time.monotonic() - t0) * 1000.0

    usage = completion.usage
    tokens_in = usage.input_tokens + getattr(usage, "cache_creation_input_tokens", 0)
    tokens_out = usage.output_tokens

    journal: dict = {
        "parser": NEWS_PARSER,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
        "latency_ms": latency_ms,
    }
    return result, journal
