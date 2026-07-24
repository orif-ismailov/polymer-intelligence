"""Environment-driven configuration for the backfill worker.

Everything the worker needs comes from environment variables — no config files,
no imports from the main app. Loading is fail-fast: a misconfigured DATABASE_URL
or a dev environment that could accidentally start a full walk raises at startup
rather than half-crawling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Raised when the environment is missing or self-contradictory."""


# The offer-detail route was confirmed from the listing pages' hrefs
# (``href='/trade/offer/<id>'``) — do not change without re-confirming against a
# live listing page. ``{id}`` is substituted per request.
DEFAULT_DETAIL_URL = "https://uzex.uz/trade/offer/{id}"
# Pin Russian rendering so stored labels are stable ("Наименование продукта",
# "Базисная цена", ...). Sets the .AspNetCore.Culture cookie; the 302 response
# still carries the Set-Cookie, so we do not need to follow the redirect.
DEFAULT_CHANGE_LANG_URL = "https://uzex.uz/Home/ChangeLang?culture=ru&returnUrl=%2F"
DEFAULT_USER_AGENT = "IMEX-Research/1.0 (+orifismailov08@gmail.com)"


def _env_str(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val.strip()


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    """Immutable resolved configuration.

    ``environment`` ("dev" | "prod") gates the safety rails. In dev the effective
    max id is hard-capped so a misconfiguration cannot start a full walk.
    """

    database_url: str
    detail_url: str
    change_lang_url: str
    user_agent: str
    worker_name: str
    min_id: int
    max_id: int
    rate_limit_rps: float
    environment: str
    dev_max_id_cap: int

    # HTTP behaviour
    http_timeout_seconds: float
    max_retries: int
    backoff_start_seconds: float
    backoff_max_seconds: float
    # How many long-backoff cycles to insist on a single failing id before
    # giving up (marking fetch_failed) and advancing. Bounds a poison id while
    # still riding out real outages. Blocked (429/403) is never given up on.
    max_hard_retries: int

    # Bookkeeping cadence
    checkpoint_every: int
    checkpoint_interval_seconds: float
    stale_lock_seconds: int

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @property
    def effective_max_id(self) -> int:
        """Max id the worker is allowed to reach given the dev cap."""
        if self.is_dev:
            return min(self.max_id, self.dev_max_id_cap)
        return self.max_id

    def detail_url_for(self, offer_id: int) -> str:
        # ``.replace`` (not ``.format``) so any other braces in the template are
        # left untouched.
        return self.detail_url.replace("{id}", str(offer_id))

    def min_request_interval(self) -> float:
        """Seconds to wait between requests to honour the global rate limit."""
        if self.rate_limit_rps <= 0:
            return 0.0
        return 1.0 / self.rate_limit_rps


def load_config() -> Config:
    """Build a :class:`Config` from the environment, validating as we go."""
    database_url = _env_str("DATABASE_URL")
    if not database_url:
        raise ConfigError("DATABASE_URL is required")

    environment = (_env_str("ENV", "prod") or "prod").lower()
    if environment not in {"dev", "prod"}:
        raise ConfigError(f"ENV must be 'dev' or 'prod', got {environment!r}")

    min_id = _env_int("MIN_ID", 1)
    max_id = _env_int("MAX_ID", 400_000)
    dev_max_id_cap = _env_int("DEV_MAX_ID_CAP", 1_000)

    if min_id < 0:
        raise ConfigError("MIN_ID must be >= 0")
    if max_id < min_id:
        raise ConfigError(f"MAX_ID ({max_id}) must be >= MIN_ID ({min_id})")

    rate_limit_rps = _env_float("RATE_LIMIT_RPS", 1.0)
    if rate_limit_rps < 0:
        raise ConfigError("RATE_LIMIT_RPS must be >= 0")

    return Config(
        database_url=database_url,
        detail_url=_env_str("UZEX_DETAIL_URL", DEFAULT_DETAIL_URL) or DEFAULT_DETAIL_URL,
        change_lang_url=_env_str("UZEX_CHANGE_LANG_URL", DEFAULT_CHANGE_LANG_URL)
        or DEFAULT_CHANGE_LANG_URL,
        user_agent=_env_str("USER_AGENT", DEFAULT_USER_AGENT) or DEFAULT_USER_AGENT,
        worker_name=_env_str("WORKER_NAME", "uzex_offer_detail") or "uzex_offer_detail",
        min_id=min_id,
        max_id=max_id,
        rate_limit_rps=rate_limit_rps,
        environment=environment,
        dev_max_id_cap=dev_max_id_cap,
        http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
        max_retries=_env_int("MAX_RETRIES", 3),
        backoff_start_seconds=_env_float("BACKOFF_START_SECONDS", 60.0),
        backoff_max_seconds=_env_float("BACKOFF_MAX_SECONDS", 3600.0),
        max_hard_retries=_env_int("MAX_HARD_RETRIES", 8),
        checkpoint_every=_env_int("CHECKPOINT_EVERY", 25),
        checkpoint_interval_seconds=_env_float("CHECKPOINT_INTERVAL_SECONDS", 30.0),
        stale_lock_seconds=_env_int("STALE_LOCK_SECONDS", 300),
    )
