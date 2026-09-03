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
from pathlib import Path

import anthropic
import instructor
from instructor.core import InstructorRetryException  # noqa: F401 — re-exported for callers

from app.core.config import settings
from app.services import llm_clients
from parsing.news_schemas import NewsArticle

NEWS_PARSER = "news_extract_tools"
NEWS_PROMPT_VERSION = "v3"
DEFAULT_MODEL: str = settings.LLM_EXTRACT_MODEL
# v2 emits analysis + recommendation + ru/uz/en translations, so the completion is
# larger than the v1 classification-only output.
NEWS_MAX_TOKENS = 3500

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_news_prompt(version: str) -> str:
    """The system prompt for a news-extract version.

    Two sources, in this order: a version an operator authored from the admin
    panel, then the `news_extract_<version>.md` that shipped in the image. The
    authored one wins because that is the one `parse_runs` has been journalling.

    The authored bodies come from `settings_service`'s in-memory snapshot, NOT
    from a query. This function runs inside `parse_news_item`'s open transaction,
    so a database read here is the nested-checkout pool deadlock that
    `settings_service.get()` is forbidden from causing — the bodies are loaded on
    the caller's own session by `refresh(db)`, at the two moments in a process's
    life when nothing else is open on it.

    Raises rather than returning `""` for a version neither source has, matching
    `parsing/prompts/loader.py`. The two disagreed once, and this side was wrong
    in a way nothing could see: an empty string is a VALID system prompt, so the
    classifier ran with no instructions at all, `parse_runs` journalled a version
    that had never been loaded, and `lru_cache` pinned the empty answer for the
    life of the process. The only symptom was news that classified badly.
    """
    from app.services import (
        settings_service,  # noqa: PLC0415 — lazy: parsing/ must not import app/ at module scope
    )

    authored = settings_service.prompt_body("news_extract", version)
    if authored is not None:
        return authored
    return _load_shipped_prompt(version)


@functools.lru_cache(maxsize=8)
def _load_shipped_prompt(version: str) -> str:
    """Read `news_extract_<version>.md` from the image. Cached; raises if absent.

    The cache sits HERE rather than on `load_news_prompt` so it only ever holds
    a file, which cannot change under a running process. Caching the resolved
    value instead would reintroduce the bug this whole design avoids: a body
    fetched before its version reached the snapshot would be pinned for the life
    of the worker, and `prompt_versions` is append-only precisely so that a
    version's text and its name can never come apart.
    """
    path = _PROMPTS_DIR / f"news_extract_{version}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"News prompt version {version!r} not found: {path}, and no authored "
            "version by that name. Create a new version rather than editing an "
            "existing one."
        )
    return path.read_text(encoding="utf-8")


_raw_client: anthropic.Anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
_client: instructor.Instructor = instructor.from_anthropic(_raw_client, mode=instructor.Mode.TOOLS)
#: `None` unless `OPENAI_API_KEY` is set. Which client a call uses is decided by
#: the model id (`llm_clients.provider_of`); both are rebound in place by
#: `llm_clients.reset()` when an operator changes a key.
_openai_client = llm_clients.build_openai_structured(settings.OPENAI_API_KEY)


def extract_news(
    text: str,
    *,
    model: str | None = None,
    prompt_version: str | None = None,
    system_prompt: str | None = None,
) -> tuple[NewsArticle, dict]:
    """Classify one news item into a NewsArticle. Calls the LLM exactly once.

    The static system prompt is cached; the news item text goes ONLY in the user turn
    (data/instruction separation). Returns (NewsArticle, journal) — write the journal
    to parse_runs for audit/replay.

    `model` and `prompt_version` are resolved per call from the live settings when
    not passed, rather than bound as default arguments. Both are operator-settable,
    and a default argument is evaluated once at import — so the old signature could
    only ever have used whatever `.env` said when the process started.

    `system_prompt` bypasses the loader entirely and is how the admin panel tries
    an UNSAVED prompt against a real article. It is deliberately not a version:
    text that was never saved has no name, so `prompt_version` in the returned
    journal stays whatever was asked for and a trial can never be mistaken for a
    run of a version that exists.

    Raises:
        FileNotFoundError: `prompt_version` names no authored or shipped version.
        InstructorRetryException: instructor exhausted its retries — caller dead-letters.
    """
    from app.services import (
        settings_service,  # noqa: PLC0415 — lazy: parsing/ must not import app/ at module scope
    )

    model = model or str(settings_service.get("llm_extract_model"))
    prompt_version = prompt_version or str(settings_service.get("news_prompt_version"))

    system_prompt = system_prompt or load_news_prompt(prompt_version)

    result, _completion, usage, latency_ms = llm_clients.structured(
        _client,
        _openai_client,
        model=model,
        system=system_prompt,
        user=text,
        response_model=NewsArticle,
        max_tokens=NEWS_MAX_TOKENS,
    )

    journal: dict = {
        "parser": NEWS_PARSER,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "cache_read_tokens": usage.cache_read_tokens,
        "latency_ms": latency_ms,
    }
    return result, journal
