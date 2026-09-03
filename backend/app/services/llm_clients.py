"""
Which LLM client is live, and in whose dialect.

Two jobs, and they arrived in that order.

**Keeping the clients in step with an operator-changed key.** Five modules build
a client at import and hold it in a module global: `parsing.extractor`,
`parsing.news_extractor`, `app.domains.news.reports`,
`app.domains.requests.analysis` and `app.domains.compliance.substance_ai`. That
was right while the key could only come from `.env` — it could not change without
a restart, so a client built once was a client built correctly. The key is
operator-settable now, and an unchanged client would make the panel lie in the
worst way: the operator pastes a working key, the panel says it is saved, and
every LLM feature goes on failing with the old one until somebody restarts the
workers. The provider looks broken, the configuration looks right, and nothing
connects the two. This is the same gap `get_didox_client` closes by comparing the
effective credential against the cached client's.

**Speaking two dialects.** The platform runs on Claude or on GPT, chosen per
model in `/admin/settings/ai`. `instructor` makes that far smaller than it
sounds: `Instructor.messages` is a property returning `self`, so
`client.messages.create_with_completion(...)` is the same call for both vendors
and every existing test patch site keeps intercepting. Only the request kwargs
and the usage field names differ, and both live in this module — `structured()`
for the four extraction call sites and `text()` for the report digest, so no
caller has to know which vendor it is talking to.

REBIND, DO NOT REPLACE. `reset()` assigns new objects to the SAME module
attributes rather than swapping the modules for factory functions. That is
deliberate: `_client` stays a module-level attribute, so the places the test
suite patches it (`patch("parsing.extractor._client")`, `patch.object(svc,
"_client")`, `patch.object(report_service._client, "messages")`) all keep
working, and the documented contract in those modules' docstrings stays true. A
lazy factory would have been tidier and would have broken every one of them.

`reset()` runs only when a key actually changes — `settings_service._invalidate`
fires it from the snapshot reload, in every process. It is never called on a hot
path, so rebuilding ten clients costs nothing that matters. (Construction makes
no network call; it only stores the key.)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol, cast

from pydantic import BaseModel

logger = logging.getLogger(__name__)

ANTHROPIC = "anthropic"
OPENAI = "openai"


# ---------------------------------------------------------------------------
# The SDK surface this module depends on
# ---------------------------------------------------------------------------
#
# Written out as protocols rather than reached for with `Any`, which
# `app.services` bans outright — and the ban is doing real work here. `instructor`
# ships no `py.typed` marker, so its client is `Any` and would have swallowed
# every mistake in this file silently. Naming the four call shapes instead says
# exactly which slice of two vendor SDKs this depends on, in one place, and it is
# a short list: two attribute hops and a method.
#
# They are `cast` onto rather than demanded of the caller. The real SDK methods
# have fully typed signatures, which do NOT match `**kwargs: object` structurally,
# so declaring a parameter as one of these would reject the very clients it
# describes. The cast is where that mismatch is admitted; the protocol still
# type-checks every use below it, which is the part that can actually be wrong.


class _StructuredCall(Protocol):
    def create_with_completion(self, **kwargs: object) -> tuple[object, object]: ...


class _Structured(Protocol):
    """An instructor-wrapped client, either vendor.

    `Instructor.messages` is a property returning `self`, which is what makes one
    call shape serve both vendors and every existing test patch site keep working.
    """

    @property
    def messages(self) -> _StructuredCall: ...


class _Create(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _RawAnthropic(Protocol):
    @property
    def messages(self) -> _Create: ...


class _OpenAIChat(Protocol):
    @property
    def completions(self) -> _Create: ...


class _RawOpenAI(Protocol):
    @property
    def chat(self) -> _OpenAIChat: ...


#: Model-id prefixes that mean OpenAI. Everything else — including an id nobody
#: here has seen — means Anthropic.
#:
#: The asymmetry is deliberate and it is the safety property of this module: an
#: operator may pin any model id from `.env` (`allowed_values` always offers the
#: live value), and before this file existed every one of them went to Anthropic.
#: Routing only on a RECOGNISED OpenAI prefix means no existing deployment can
#: have its provider changed by this change. A typo'd `gpt-4o` still fails at
#: OpenAI with OpenAI's own error; a typo'd `claude-…` still fails at Anthropic.
_OPENAI_PREFIXES: tuple[str, ...] = ("gpt-", "o1", "o3", "o4", "chatgpt-")

#: OpenAI models that reject `temperature` — the reasoning families accept only
#: the default, and sending `temperature=0` is a 400, not a nudge that is
#: ignored. Extraction wants determinism, so this is a real loss on those models
#: rather than a formality; it is why the cheaper non-reasoning ids are the ones
#: offered first in the panel.
_OPENAI_FIXED_TEMPERATURE_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")


def provider_of(model: str) -> str:
    """`ANTHROPIC` or `OPENAI`, derived from the model id.

    Derived, not configured. A separate provider switch could disagree with the
    model it is supposed to describe, and "two places that must agree about one
    fact" is a failure this repo has already paid for twice — the two `.env`
    files that disagreed on ten keys, and the settings default written as a
    Python literal beside the row that overrode it.
    """
    name = model.strip().lower()
    return OPENAI if name.startswith(_OPENAI_PREFIXES) else ANTHROPIC


# ---------------------------------------------------------------------------
# Calling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    """Token counts, normalised so a `parse_runs` row means one thing.

    The two vendors do not agree on what "input tokens" counts. Anthropic reports
    `input_tokens` EXCLUDING cache reads and bills them separately; OpenAI's
    `prompt_tokens` INCLUDES them. Left alone, an OpenAI call would report the
    same tokens twice — once in `tokens_in` and once in `cache_read_tokens` —
    and `/admin/llm-spend` sums exactly those columns.
    """

    tokens_in: int
    tokens_out: int
    cache_read_tokens: int

    @property
    def total(self) -> int:
        """What the daily budget counts (`parsing/budget.py`)."""
        return self.tokens_in + self.tokens_out


class NoClient(Exception):
    """The model names a provider this process has no client for."""


def _pick[C](anthropic_client: C, openai_client: C | None, model: str) -> tuple[C, str]:
    """The client for `model`, and the provider it belongs to.

    Both clients are passed in by the caller rather than looked up here, and that
    is the whole reason the existing tests still work: `patch.object(substance_ai,
    "_client")` replaces the attribute the CALLER reads, so a lookup inside this
    module would step in front of it and every mocked LLM test would start making
    real calls.
    """
    provider = provider_of(model)
    if provider == ANTHROPIC:
        return anthropic_client, ANTHROPIC
    if openai_client is None:
        # Unreachable through the panel — the `Settings` validator refuses a GPT
        # model with no OpenAI key at the write. Reachable by editing `.env` by
        # hand, so it says which of the two things is missing.
        raise NoClient(f"{model} needs an OpenAI API key, and OPENAI_API_KEY is not set.")
    return openai_client, OPENAI


def _request_kwargs(
    provider: str, model: str, system: str, user: str, max_tokens: int
) -> dict[str, object]:
    """The same call, in each vendor's dialect.

    Three differences, and each one is a 400 rather than a silent degradation —
    which is the good case, but only against the live API. None of them can be
    caught by a mocked test, so this function is the thing to check first when a
    newly offered model refuses every request.

    1. Anthropic takes the system prompt as its own `system` parameter; OpenAI
       takes it as the first message.
    2. Anthropic's `max_tokens` is OpenAI's `max_completion_tokens`.
    3. OpenAI's reasoning models reject `temperature` outright.

    `cache_control` stays on the Anthropic branch only. It is not portable —
    OpenAI caches automatically with no parameter — and it is why this
    deployment's monthly spend is what it is, so it is applied wherever it works
    rather than dropped for the symmetry of a single code path.
    """
    if provider == ANTHROPIC:
        return {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": user}],
        }

    kwargs: dict[str, object] = {
        "model": model,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if not model.strip().lower().startswith(_OPENAI_FIXED_TEMPERATURE_PREFIXES):
        kwargs["temperature"] = 0
    return kwargs


def usage_of(completion: object) -> Usage:
    """Read token counts off a completion from either vendor.

    A completion with no usage block at all counts as zero rather than raising:
    the callers journal what comes back here, and a missing counter must not turn
    a successful classification into a failed one.
    """
    raw = getattr(completion, "usage", None)
    if raw is None:
        return Usage(tokens_in=0, tokens_out=0, cache_read_tokens=0)
    if hasattr(raw, "input_tokens"):  # Anthropic
        return Usage(
            tokens_in=raw.input_tokens + (getattr(raw, "cache_creation_input_tokens", 0) or 0),
            tokens_out=raw.output_tokens,
            cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        )
    cached = getattr(getattr(raw, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    # `prompt_tokens` includes the cached ones; subtracting them here is what
    # makes `tokens_in` mean the same thing as it does on the Anthropic branch.
    return Usage(
        tokens_in=max(0, (raw.prompt_tokens or 0) - cached),
        tokens_out=raw.completion_tokens or 0,
        cache_read_tokens=cached,
    )


def structured[T: BaseModel](
    anthropic_client: object,
    openai_client: object | None,
    *,
    model: str,
    system: str,
    user: str,
    response_model: type[T],
    max_tokens: int,
    max_retries: int = 2,
) -> tuple[T, object, Usage, float]:
    """One structured extraction call. Returns `(result, completion, usage, ms)`.

    The four extraction call sites were byte-identical before this existed —
    same kwargs, same `create_with_completion`, and the same six lines of usage
    arithmetic copied into each. They now differ only in their prompt, their
    response model and their token ceiling, which is the whole of what actually
    differs between them.

    `completion` comes back too because `parsing.extractor` journals
    `completion.model_dump()` verbatim for eval replay.
    """
    picked, provider = _pick(anthropic_client, openai_client, model)
    client = cast(_Structured, picked)
    kwargs = _request_kwargs(provider, model, system, user, max_tokens)

    started = time.monotonic()
    result, completion = client.messages.create_with_completion(
        response_model=response_model,
        max_retries=max_retries,
        **kwargs,
    )
    latency_ms = (time.monotonic() - started) * 1000.0
    return cast(T, result), completion, usage_of(completion), latency_ms


def text(
    anthropic_client: object,
    openai_client: object | None,
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
) -> tuple[str, Usage]:
    """One plain-text call, for a caller that parses the response itself.

    The report digest asks for strict JSON and reads it back by hand rather than
    through a `response_model`, so it holds a RAW vendor client — and the raw
    clients are where the two SDKs stop looking alike: `.messages.create()`
    returning content blocks against `.chat.completions.create()` returning
    choices.

    Returns the usage alongside the text because the report is the single most
    expensive call this platform makes — ~6.5k output tokens, twice a day — and
    it was the only LLM caller recording no token count anywhere. Returning a
    bare `str` is what made that invisible.
    """
    provider = provider_of(model)
    kwargs = _request_kwargs(provider, model, system, user, max_tokens)

    # Picked by hand rather than through `_pick`, because unlike the instructor
    # clients these two do not share a shape — that is the whole reason this
    # function exists next to `structured` instead of inside it.
    if provider == ANTHROPIC:
        # The raw Anthropic client takes the system prompt as a plain string here;
        # the block form with `cache_control` is for the instructor path, where
        # the prompt is reused across thousands of calls. A report runs twice a day.
        kwargs["system"] = system
        response = cast(_RawAnthropic, anthropic_client).messages.create(**kwargs)
        parts = [
            getattr(block, "text", "")
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        return " ".join(parts).strip(), usage_of(response)

    if openai_client is None:
        raise NoClient(f"{model} needs an OpenAI API key, and OPENAI_API_KEY is not set.")
    response = cast(_RawOpenAI, openai_client).chat.completions.create(**kwargs)
    usage = usage_of(response)
    choices = getattr(response, "choices", [])
    if not choices:
        # Still the real usage: an empty answer was paid for like any other.
        return "", usage
    return str(getattr(choices[0].message, "content", "") or "").strip(), usage


# ---------------------------------------------------------------------------
# Keeping the clients current
# ---------------------------------------------------------------------------

#: `(module path, does it need the instructor wrapper?)`.
#:
#: `app.domains.news.reports` is the odd one out — it holds RAW clients and calls
#: `.messages.create()` / `.chat.completions.create()`, where the other four hold
#: instructor-wrapped clients and call `.messages.create_with_completion()`.
#: Listing the difference here beats five near-identical reset functions.
_CLIENTS: tuple[tuple[str, bool], ...] = (
    ("parsing.extractor", True),
    ("parsing.news_extractor", True),
    ("app.domains.news.reports", False),
    ("app.domains.requests.analysis", True),
    ("app.domains.compliance.substance_ai", True),
)


def live_key(provider: str = ANTHROPIC) -> str:
    """The key this deployment is running for `provider`: the override, else `.env`."""
    from app.services import settings_service  # noqa: PLC0415 — avoids an import cycle

    key = "openai_api_key" if provider == OPENAI else "anthropic_api_key"
    return settings_service.get_str(key)


def reset() -> None:
    """Rebuild every client from the current keys.

    Only rebuilds modules that are already imported. A process that has never
    touched `parsing.extractor` has no stale client to fix, and importing one
    here to fix it would drag the SDKs into processes that do not use them —
    `sys.modules` is the honest question to ask.

    Never raises. A failure to rebuild one client must not take down the write
    that triggered it, or an operator correcting a key would be blocked by the
    very thing they are correcting.
    """
    import sys  # noqa: PLC0415

    anthropic_key = live_key(ANTHROPIC)
    openai_key = live_key(OPENAI)
    for module_path, wrapped in _CLIENTS:
        module = sys.modules.get(module_path)
        if module is None:
            continue
        try:
            _rebind(module, anthropic_key, openai_key, wrapped=wrapped)
        except Exception:  # noqa: BLE001 — one bad rebind must not block the others
            # `extra={"module": …}` would raise: `module` is a reserved LogRecord
            # attribute, so the log line meant to swallow the failure would itself
            # break the "never raises" contract.
            logger.warning("llm_clients.rebind_failed client_module=%s", module_path)


def _rebind(module: object, anthropic_key: str, openai_key: str, *, wrapped: bool) -> None:
    import anthropic  # noqa: PLC0415
    import instructor  # noqa: PLC0415

    raw = anthropic.Anthropic(api_key=anthropic_key)
    if hasattr(module, "_raw_client"):
        module._raw_client = raw  # (`hasattr` above is what narrows this for mypy)
    module._client = (  # type: ignore[attr-defined]
        instructor.from_anthropic(raw, mode=instructor.Mode.TOOLS) if wrapped else raw
    )
    module._openai_client = (  # type: ignore[attr-defined]
        build_openai_structured(openai_key) if wrapped else build_openai_raw(openai_key)
    )


def _raw_openai(key: str) -> object | None:
    """An `openai.OpenAI`, or `None` when there is no key.

    `None` rather than a client that fails on first use, because
    `openai.OpenAI(api_key="")` RAISES at construction (`OpenAIError: Missing
    credentials`). Left unguarded that would make `_rebind` throw for every
    module in every process on every deployment without an OpenAI key — which
    today is all of them — turning `reset()`'s warning from an alarm into
    background noise.
    """
    import openai  # noqa: PLC0415

    if not key.strip():
        return None
    return openai.OpenAI(api_key=key)


def build_openai_structured(key: str) -> object | None:
    """An instructor-wrapped OpenAI client for the four extraction modules.

    Public because those modules call it at IMPORT, beside the Anthropic client
    they already build there. `reset()` alone would not do: it runs when a key
    CHANGES, so a process that starts with a perfectly good `OPENAI_API_KEY` in
    `.env` and is never reconfigured would hold `None` and refuse every GPT call.
    The key is passed in rather than read here so this stays importable from
    `parsing/`, which must not pull `settings_service` in at module scope.
    """
    import instructor  # noqa: PLC0415
    import openai  # noqa: PLC0415

    raw = _raw_openai(key)
    if raw is None:
        return None
    client: object = instructor.from_openai(
        cast(openai.OpenAI, raw), mode=instructor.Mode.TOOLS
    )
    return client


def build_openai_raw(key: str) -> object | None:
    """A bare OpenAI client, for the report digest — see `text()`."""
    return _raw_openai(key)


# ---------------------------------------------------------------------------
# What a model costs
# ---------------------------------------------------------------------------

#: Approximate list prices, USD per 1M tokens.
#:
#: ESTIMATES, for a rough $/day figure. Every endpoint that uses them echoes the
#: table back in its response, so a reader can see what the number was computed
#: from rather than trusting it — the token and call counts beside them are exact.
#:
#: Every model either dropdown offers belongs here (`EXTRACT_MODELS` /
#: `REPORT_MODELS` in `settings_service`). It held two entries while it was
#: written for two models, so everything an operator could actually select fell
#: through to `_DEFAULT_RATE` and was costed as Sonnet — Haiku overstated
#: fivefold, Opus understated.
#:
#: Here rather than in a router because two callers now need it
#: (`/admin/llm-spend` and `/admin/analytics/ai`), and because this module already
#: owns "what a model IS". Two rate tables would have disagreed within a month.
RATE_USD_PER_MTOK: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
    "claude-sonnet-4-5": {"in": 3.0, "out": 15.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-sonnet-5": {"in": 3.0, "out": 15.0},
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},
    "claude-opus-5": {"in": 5.0, "out": 25.0},
    # OpenAI
    "gpt-4.1-mini": {"in": 0.4, "out": 1.6},
    "gpt-4.1": {"in": 2.0, "out": 8.0},
    "gpt-5-mini": {"in": 0.25, "out": 2.0},
    "gpt-5": {"in": 1.25, "out": 10.0},
}
_DEFAULT_RATE: dict[str, float] = {"in": 3.0, "out": 15.0}


def rate_for(model: str) -> dict[str, float]:
    """Best-effort rate lookup: exact, then longest known prefix, else the default.

    Longest wins, and it has to: `gpt-5` is a prefix of `gpt-5-mini`, so a
    first-match scan would cost an unlisted `gpt-5-nano` at the flagship rate
    purely because of dict ordering. The old loop returned the first match while
    saying it returned the longest — invisible while every key was disjoint.
    """
    if model in RATE_USD_PER_MTOK:
        return RATE_USD_PER_MTOK[model]
    matches = [key for key in RATE_USD_PER_MTOK if model.startswith(key)]
    if matches:
        return RATE_USD_PER_MTOK[max(matches, key=len)]
    return _DEFAULT_RATE


def est_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Estimated USD for one model's traffic. See `RATE_USD_PER_MTOK`."""
    rate = rate_for(model)
    return round(tokens_in / 1_000_000 * rate["in"] + tokens_out / 1_000_000 * rate["out"], 4)


# ---------------------------------------------------------------------------
# Checking a key before it is stored
# ---------------------------------------------------------------------------


class KeyRejected(Exception):
    """The provider refused the key. The message is the provider's own reason."""


def verify(key: str, provider: str = ANTHROPIC) -> None:
    """Check a key with its provider before it is stored. Raises `KeyRejected`.

    Reads the models endpoint, which costs no tokens — the point is to prove the
    key authenticates, not to generate anything.

    Refusing an unverifiable key is the deliberate trade. These credentials drive
    news classification, the daily reports, buyer-request analysis and the
    substance hint, and each of those DEGRADES rather than erroring when the LLM
    call fails: the news simply classifies badly, the report falls back to
    rule-based summaries. So a typo here is expensive and quiet, and the cost of
    the alternative — not being able to rotate a key while the provider is
    unreachable — is a wait, not a loss. The key already in use keeps working
    throughout.
    """
    if not key.strip():
        raise KeyRejected("The API key cannot be empty.")

    if provider == OPENAI:
        import openai  # noqa: PLC0415

        try:
            openai.OpenAI(api_key=key, timeout=15.0).models.list()
        except openai.AuthenticationError as exc:
            raise KeyRejected(f"OpenAI rejected the key: {_reason(exc)}") from exc
        except openai.APIStatusError as exc:
            raise KeyRejected(f"OpenAI answered {exc.status_code}: {_reason(exc)}") from exc
        except Exception as exc:  # noqa: BLE001 — network, DNS, timeout
            raise KeyRejected(f"Could not reach OpenAI to check the key: {exc}") from exc
        return

    import anthropic  # noqa: PLC0415

    try:
        anthropic.Anthropic(api_key=key, timeout=15.0).models.list(limit=1)
    except anthropic.AuthenticationError as exc:
        raise KeyRejected(f"Anthropic rejected the key: {_reason(exc)}") from exc
    except anthropic.APIStatusError as exc:
        raise KeyRejected(f"Anthropic answered {exc.status_code}: {_reason(exc)}") from exc
    except Exception as exc:  # noqa: BLE001 — network, DNS, timeout
        raise KeyRejected(f"Could not reach Anthropic to check the key: {exc}") from exc


def _reason(exc: Exception) -> str:
    """The provider's own words, trimmed — never the key.

    Prefers the message inside the response body ("API key is invalid.") over the
    SDK's `.message`, which renders the whole envelope as a Python repr —
    accurate but unreadable in a red banner an operator is meant to act on.

    Two shapes, because the vendors nest it differently: Anthropic's `body` is
    the full envelope (`{"error": {"message": …}}`), OpenAI's is already the inner
    error (`{"message": …}`). Checked in that order; a miss falls through to the
    repr, which is ugly but never wrong.

    Capped either way, and only ever a message: an SDK error renders the REQUEST
    body in some paths, and the operator needs to know why it was refused, not to
    see the string they just pasted read back to them.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:200]
        if body.get("message"):
            return str(body["message"])[:200]
    message = getattr(exc, "message", None) or str(exc)
    return str(message)[:200]
