"""HTTP fetching for the backfill worker.

A thin wrapper over a single persistent-cookie ``httpx.Client``:

* pins Russian rendering once at startup via ``/Home/ChangeLang?culture=ru``
  (the 302 still carries the ``.AspNetCore.Culture`` Set-Cookie),
* performs up to ``max_retries`` per-id attempts with a small exponential backoff
  for transient network errors and 5xx,
* classifies each outcome so the walker can decide between a quick continue and a
  long politeness backoff.

The long 60s→1h backoff (429/403 / sustained outage) is driven by the *walker*,
not here — this module only reports what happened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import Config
from .log import log

# What kind of thing happened for one id.
OUTCOME_FETCHED = "fetched"  # we have a body to parse (2xx)
OUTCOME_HTTP_NOT_FOUND = "http_not_found"  # server said 404
OUTCOME_BLOCKED = "blocked"  # 429/403 — walker should back off long and retry
OUTCOME_FAILED = "failed"  # network error / 5xx persisted through retries

# Per-id retry backoff is deliberately small (seconds) and separate from the
# walker's long politeness backoff.
_SMALL_BACKOFF_BASE = 2.0
# Body sanity cap; real detail pages are ~70 KB.
_MAX_BODY_BYTES = 25 * 1024 * 1024


@dataclass
class FetchResult:
    outcome: str
    http_status: int | None = None
    final_url: str | None = None
    text: str | None = None
    error: str | None = None


class Fetcher:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = httpx.Client(
            headers={
                "User-Agent": config.user_agent,
                "Accept-Language": "ru,ru-RU;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=httpx.Timeout(config.http_timeout_seconds),
            follow_redirects=True,  # so final_url reflects any redirect
        )

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- language pin ------------------------------------------------------
    def pin_language(self) -> bool:
        """Hit ChangeLang once to pin culture=ru. Non-fatal on failure."""
        try:
            resp = self._client.get(self._config.change_lang_url, follow_redirects=False)
        except httpx.HTTPError as exc:
            log("pin_language_failed", error=str(exc))
            return False
        culture = self._client.cookies.get(".AspNetCore.Culture")
        log("pin_language", http_status=resp.status_code, culture_cookie=culture)
        return culture is not None

    # -- per-id fetch ------------------------------------------------------
    def fetch(self, offer_id: int) -> FetchResult:
        url = self._config.detail_url_for(offer_id)
        max_retries = self._config.max_retries
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_retries:
                    time.sleep(_SMALL_BACKOFF_BASE * (2**attempt))
                    continue
                return FetchResult(outcome=OUTCOME_FAILED, error=last_error)

            status = resp.status_code
            final_url = str(resp.url)

            if status in (403, 429):
                return FetchResult(
                    outcome=OUTCOME_BLOCKED, http_status=status, final_url=final_url
                )
            if status == 404:
                return FetchResult(
                    outcome=OUTCOME_HTTP_NOT_FOUND, http_status=status, final_url=final_url
                )
            if 500 <= status < 600:
                last_error = f"HTTP {status}"
                if attempt < max_retries:
                    time.sleep(_SMALL_BACKOFF_BASE * (2**attempt))
                    continue
                return FetchResult(
                    outcome=OUTCOME_FAILED, http_status=status, final_url=final_url, error=last_error
                )
            if 200 <= status < 300:
                if len(resp.content) > _MAX_BODY_BYTES:
                    return FetchResult(
                        outcome=OUTCOME_FAILED,
                        http_status=status,
                        final_url=final_url,
                        error="body too large",
                    )
                return FetchResult(
                    outcome=OUTCOME_FETCHED,
                    http_status=status,
                    final_url=final_url,
                    text=resp.text,
                )
            # Unexpected 4xx / other — treat as failed (retryable later).
            return FetchResult(
                outcome=OUTCOME_FAILED,
                http_status=status,
                final_url=final_url,
                error=f"unexpected HTTP {status}",
            )

        # Unreachable, but keeps the type checker honest.
        return FetchResult(outcome=OUTCOME_FAILED, error=last_error)
