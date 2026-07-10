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
    # Prompt version pin — stored verbatim in parse_runs.prompt_version for replay.
    # When the prompt changes, create parsing/prompts/extract_vN.md and update this.
    LLM_PROMPT_VERSION: str = "v1"
    # When True, UZEX rows that the rule-based dictionary does NOT recognize are
    # routed through the LLM extractor (like Telegram) instead of being marked
    # irrelevant + queued for manual classification. The LLM emits canonical product
    # codes (e.g. "PVC") which the existing synonym dictionary resolves to product_id,
    # so polymers in raw Russian/Uzbek text are caught without per-string hand-mapping.
    # Off by default: it spends Anthropic tokens per unrecognized row (budget-gated).
    UZEX_LLM_FALLBACK_ENABLED: bool = False
    # ── Request AI analysis (Phase 5 — buyer-request match/demand/recommendation) ─
    # When True, a submitted buyer request is analysed by the LLM (match_score,
    # demand_level, recommendation) and the result is stamped into requests.ai for the
    # dashboard request-detail "AI-анализ" panel. Off → the panel keeps honest
    # placeholders. Budget-gated like the extractor (spends Anthropic tokens per request).
    REQUEST_AI_ANALYSIS_ENABLED: bool = True
    # Telegram group/chat that receives a notification for each new buyer request.
    # Numeric chat id (e.g. -1001234567890 for a supergroup) — NOT an invite link;
    # the bot must be a member of the group. Unset (None) → notifications disabled.
    REQUEST_NOTIFY_CHAT_ID: int | None = None
    # Optional forum-topic (message_thread_id) routing inside REQUEST_NOTIFY_CHAT_ID.
    # When the notify group is a Telegram forum (topics enabled), buyer-side
    # notifications (new purchase requests + offer inquiries) go to NOTIFY_TOPIC_BUYERS
    # and seller-side notifications (new/edited offers) go to NOTIFY_TOPIC_SELLERS.
    # Unset (None) → posts to the group's General topic (no thread). If a configured
    # topic is invalid/closed, delivery falls back to General instead of being dropped.
    NOTIFY_TOPIC_BUYERS: int | None = None
    NOTIFY_TOPIC_SELLERS: int | None = None
    REQUEST_AI_ANALYSIS_MODEL: str = "claude-haiku-4-5"
    REQUEST_AI_ANALYSIS_PROMPT_VERSION: str = "v1"
    # Conservative per-request token reservation for the budget guard.
    REQUEST_AI_TOKEN_ESTIMATE: int = 1500

    # ── Telegram bot ──────────────────────────────────────────────────────────
    BOT_TOKEN: str
    WEBHOOK_SECRET: str
    # Public bot @handle (WITHOUT the leading @), e.g. "imex_ai_bot". Needed by the
    # browser Telegram Login Widget (data-telegram-login) so the webapp can
    # authenticate visitors who open it outside Telegram. Delivered to the static
    # bundle at runtime via GET /webapp/auth/config. Empty → browser login disabled.
    # NOTE: the bot's domain must also be registered via BotFather /setdomain.
    BOT_USERNAME: str = ""
    # Lifetime of the browser client-session cookie issued after a successful Login
    # Widget authentication (seconds). Default 30 days. There is no refresh flow for
    # low-privilege client sessions; they simply re-auth via the widget on expiry.
    CLIENT_SESSION_TTL_SECONDS: int = 2_592_000

    # ── Telegram userbot ──────────────────────────────────────────────────────
    TG_API_ID: int
    TG_API_HASH: str
    # Session string generated once locally via the interactive StringSession login
    # flow (see userbot/session.py). Stored in .env, NEVER committed (T-05-05).
    # Empty default so the API/worker/beat services can start without it;
    # the userbot raises a clear error at startup if this is empty.
    TG_SESSION_STRING: str = ""
    # How often the userbot re-reads the enabled channel list (seconds).
    # Default 600 = ~10 min — ROADMAP SC#1 "rereads the channel list every ~10 min".
    USERBOT_CHANNEL_REREAD_SECONDS: int = 600
    # How often the userbot writes its Redis heartbeat (seconds).
    USERBOT_HEARTBEAT_SECONDS: int = 60

    # ── Auth ──────────────────────────────────────────────────────────────────
    JWT_SECRET: str

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Explicit non-wildcard list of allowed origins for credentialed CORS requests.
    # Never default to ["*"] — wildcard with allow_credentials=True is both a
    # security misconfiguration and non-functional per the CORS spec (CR-04).
    # Parse a comma-separated env var, e.g.:
    #   CORS_ALLOWED_ORIGINS=http://localhost:3000,https://dashboard.example.com
    # Union[list[str], str] allows pydantic-settings to pass the raw comma-separated
    # env string through to _parse_cors_origins (list[str] alone triggers JSON parsing).
    CORS_ALLOWED_ORIGINS: list[str] | str = ["http://localhost:3000"]

    # ── S3 / MinIO file storage ───────────────────────────────────────────────
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str = "polymer-files"

    # ── Telegram Web App ──────────────────────────────────────────────────────
    # Externally reachable Web App base URL (ai-imex.com) used to build status-push
    # deep-link buttons and the WebApp launch button. Empty default keeps the test
    # suite green (no live infrastructure needed); set in .env for production.
    PUBLIC_WEBAPP_URL: str = ""
    # Externally reachable API base URL (api.ai-imex.com) used to register the
    # Telegram webhook. Falls back to PUBLIC_WEBAPP_URL when empty (single-domain
    # deployments); set in .env once the API has its own domain.
    PUBLIC_API_URL: str = ""
    # Telegram news channel id (e.g. "@petroai_news" or a numeric -100… chat id) the
    # approved daily report is posted to. Empty → channel publishing is a no-op
    # (dev/test never call Telegram). Phase 3 news engine.
    NEWS_CHANNEL_ID: str = ""
    # 24-hour TTL for initData HMAC verification (dev-spec §3.2, T-03-02).
    # initData older than this number of seconds is rejected as potentially replayed.
    TELEGRAM_INIT_DATA_TTL_SECONDS: int = 86400

    # ── Ingest HTTP tunables (SPEC §2 collector rules) ────────────────────────
    # Consumed by the httpx client in 02-03 and by the Celery worker tasks.
    # All have safe defaults; override via .env for per-environment tuning.
    INGEST_HTTP_TIMEOUT_SECONDS: int = 30
    INGEST_HTTP_RETRIES: int = 3
    INGEST_USER_AGENT: str = "PolymerIntelligence/1.0 (+contact@polymer.example)"
    INGEST_PER_HOST_DELAY_SECONDS: float = 2.0

    # ── Timezone / display ────────────────────────────────────────────────────
    TZ_DISPLAY: str = "Asia/Tashkent"

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Runtime ───────────────────────────────────────────────────────────────
    # When true, the FastAPI lifespan runs `alembic upgrade head` (advisory-locked,
    # see app.entrypoint.run_migrations) on startup so a fresh `docker compose up`
    # auto-applies the locked schema (SC#2). Default false so the test suite and CI
    # — which build the app via TestClient without a migratable database — never
    # attempt migrations at import/startup. The dev compose sets this to "true".
    RUN_MIGRATIONS_ON_STARTUP: bool = False

    # When True, the FastAPI app exposes /docs, /redoc, and /openapi.json.
    # Must be False in production so the OpenAPI schema (full attack-surface map)
    # is not publicly accessible (WR-03 / REQ-nfr-security).
    # Set DEBUG=true in .env for local development.
    DEBUG: bool = False

    @field_validator("JWT_SECRET")
    @classmethod
    def _jwt_secret_min_length(cls, v: str) -> str:
        """Reject JWT secrets shorter than 32 characters at startup.

        A short JWT secret makes HS256 tokens brute-forceable, defeating T-03-02.
        The CI placeholder (ci-jwt-secret-placeholder-32chars!!) satisfies this.
        WR-01: fail fast at startup rather than allowing a weak secret to persist.
        """
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @field_validator(
        "REQUEST_NOTIFY_CHAT_ID",
        "NOTIFY_TOPIC_BUYERS",
        "NOTIFY_TOPIC_SELLERS",
        mode="before",
    )
    @classmethod
    def _empty_chat_id_to_none(cls, v: object) -> object:
        """Treat an empty/whitespace env value as unset (None) so a blank
        REQUEST_NOTIFY_CHAT_ID= / NOTIFY_TOPIC_* in .env disables that routing
        instead of failing int coercion at startup."""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS from a comma-separated string or return list as-is.

        Accepts:
        - A list (already parsed by pydantic-settings from JSON env var): returned as-is.
        - A comma-separated string (typical .env value): split on "," and strip whitespace,
          dropping empty segments.

        Never produces ["*"] — the default is a non-wildcard list (CR-04, T-03-05).
        The Union[list[str], str] field type allows pydantic-settings to pass the raw string
        through to this validator rather than failing on JSON decode.
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        # v is Union[list[str], str] at runtime (validated by pydantic field type);
        # mypy sees `object` from the @classmethod generic — cast to narrow safely.
        if isinstance(v, list):
            return [str(item) for item in v]
        return []  # unreachable at runtime; satisfies mypy exhaustiveness

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
# BaseSettings reads required fields from environment; mypy can't see that.
settings = Settings()  # type: ignore[call-arg]
