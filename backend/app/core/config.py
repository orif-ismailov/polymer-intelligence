"""
Application settings — reads the full ENV contract from deploy/.env.example.

Secrets (JWT_SECRET, BOT_TOKEN, WEBHOOK_SECRET, TG_API_ID, TG_API_HASH,
ANTHROPIC_API_KEY, S3_ACCESS_KEY, S3_SECRET_KEY) are required with no default
so misconfiguration fails fast at startup rather than at first use.

REQ-nfr-security: no secret literals appear in tracked source; secrets are
loaded only from an untracked .env file (see deploy/.env.example contract).
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str

    # ── Anthropic / LLM ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str
    LLM_EXTRACT_MODEL: str = "claude-haiku-4-5"
    LLM_REPORT_MODEL: str = "claude-sonnet-4-5"
    LLM_DAILY_TOKEN_LIMIT: int = 500_000

    # ── Telegram bot ──────────────────────────────────────────────────────────
    BOT_TOKEN: str
    WEBHOOK_SECRET: str

    # ── Telegram userbot ──────────────────────────────────────────────────────
    TG_API_ID: int
    TG_API_HASH: str

    # ── Auth ──────────────────────────────────────────────────────────────────
    JWT_SECRET: str

    # ── S3 / MinIO file storage ───────────────────────────────────────────────
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str = "polymer-files"

    # ── Timezone / display ────────────────────────────────────────────────────
    TZ_DISPLAY: str = "Asia/Tashkent"

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    @field_validator("TZ_DISPLAY")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


# Single module-level accessor — import `settings` everywhere, do not call Settings() twice.
settings = Settings()
