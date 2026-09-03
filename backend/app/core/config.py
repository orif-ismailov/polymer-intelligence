"""
Application settings — reads the full ENV contract from deploy/.env.example.

Secrets (JWT_SECRET, BOT_TOKEN, WEBHOOK_SECRET, TG_API_ID, TG_API_HASH,
ANTHROPIC_API_KEY, S3_ACCESS_KEY, S3_SECRET_KEY) are required with no default
so misconfiguration fails fast at startup rather than at first use.

REQ-nfr-security: no secret literals appear in tracked source; secrets are
loaded only from an untracked .env file (see deploy/.env.example contract).
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    # ONE env file, at the repo root, anchored to the source tree.
    #
    # This was `env_file=".env"`, which pydantic resolves against the CURRENT
    # WORKING DIRECTORY — and this repo had two such files: `./.env` (passed to
    # compose) and `./backend/.env` (what a local `uv run uvicorn` picked up,
    # since `scripts/dev.sh` starts it from `backend/`). Which one configured
    # the app therefore depended on the directory you launched from, and the two
    # disagreed on ten keys including `JWT_SECRET`, `BOT_TOKEN` and the S3
    # credentials. The test suite still carries a scar from it: `conftest` pins
    # `LLM_DAILY_TOKEN_LIMIT` and `OTP_MAX_SENDS_PER_DAY` because a developer's
    # `backend/.env` silently substituted its own values, failing tests on one
    # machine and nowhere else.
    #
    # `backend/.env` has been merged into the root file and deleted. Anchoring
    # to `REPO_ROOT` rather than a relative path is what makes that stick: a
    # relative `.env` would quietly start reading a NEW `backend/.env` the moment
    # anyone created one, which is exactly how the split re-forms.
    #
    # Real environment variables still win over the file, so compose (which sets
    # DATABASE_URL/REDIS_URL/S3_ENDPOINT via `environment:`) and CI are
    # unaffected.
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    # SQLAlchemy pool size, PER PROCESS. Multiply by (api workers + celery
    # workers) before comparing against Postgres `max_connections` — see the
    # arithmetic in app/core/db.py. Lower than the pre-multi-worker default of
    # 10/20 precisely because there are now several processes rather than one.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str

    # ── LLM providers ────────────────────────────────────────────────────────
    # Anthropic is the required one: it is what the platform ships running, and a
    # deployment with no LLM key at all should fail at startup rather than
    # classify every article badly and never say why.
    ANTHROPIC_API_KEY: str
    # Optional, and conditionally required — see `_require_openai_key_for_gpt`.
    # A deployment that never selects a GPT model needs no value, exactly like
    # DIDOX_PARTNER_TOKEN and ESCROW_WEBHOOK_SECRET below.
    OPENAI_API_KEY: str = ""  # [SECRET] required only when a GPT model is selected
    # Either vendor. `llm_clients.provider_of` derives the provider from the id,
    # so these two fields are the only place the choice is recorded.
    LLM_EXTRACT_MODEL: str = "claude-haiku-4-5"
    LLM_REPORT_MODEL: str = "claude-sonnet-4-5"
    LLM_DAILY_TOKEN_LIMIT: int = 500_000
    # Prompt version pin — stored verbatim in parse_runs.prompt_version for replay.
    # When the prompt changes, create parsing/prompts/extract_vN.md and update this.
    LLM_PROMPT_VERSION: str = "v1"
    # Daily-digest prompt version (parsing/prompts/report_vN.md) — versioned separately
    # from the extractor prompt so the two can evolve independently.
    REPORT_PROMPT_VERSION: str = "v6"
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

    # ── Company verification & portal (R1) ────────────────────────────────────
    # Fernet key (urlsafe base64, ≥32 chars) that encrypts company bank account
    # numbers (R1) and PINFL (R3) at the app layer. Required, no default — a
    # misconfigured key must fail fast, not silently store plaintext. Generate with
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    VERIFICATION_ENC_KEY: str
    # SMS provider for phone-OTP auth. "console" (default) logs the code at INFO for
    # dev/CI; "eskiz" sends real SMS via Eskiz.uz and requires ESKIZ_EMAIL/PASSWORD.
    SMS_PROVIDER: str = "console"
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""
    # DEV/DEMO ONLY — a fixed OTP code, so a demo login does not need the code
    # fished out of a worker log every time. Set it to "000000" in a dev .env.
    #
    # Empty by default, and honoured ONLY when `DEBUG` is on AND `SMS_PROVIDER` is
    # `console` — the same double gate as the `/portal/auth/otp/peek` hook, because
    # this has the same consequence: a predictable OTP means anyone who knows a
    # phone number can sign in as its owner. Both halves of that gate live in
    # `otp_service._dev_fixed_code`, and `_reject_fixed_otp_with_real_sms` below
    # refuses the one combination that can only be a mistake.
    #
    # MUST stay empty in production.
    OTP_DEV_CODE: str = ""
    # OTP tunables (Redis-backed, see app/services/otp_service.py).
    OTP_TTL_SECONDS: int = 300
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_SENDS_PER_DAY: int = 5
    OTP_MAX_VERIFY_ATTEMPTS: int = 5
    # Portal refresh-cookie lifetime (days). Short access JWT (aud=portal) rides on top.
    PORTAL_SESSION_TTL_DAYS: int = 30
    # Telegram group/chat that receives a verification-case card per submitted case.
    # Falls back to REQUEST_NOTIFY_CHAT_ID when unset. None → group notify disabled.
    VERIFICATION_NOTIFY_CHAT_ID: int | None = None

    # ── E-IMZO verification rails (R3) ────────────────────────────────────────
    # Base URL of the UNICON e-imzo-server sidecar (internal network, no published
    # ports). All PKCS#7 verification is delegated there — stock crypto libraries
    # cannot verify the national O'zDSt algorithms. Non-secret (a service name);
    # defaults to the compose service so dev/CI need no override.
    EIMZO_SERVER_URL: str = "http://eimzo-server:8080"
    # Lifetime of a one-time signing challenge stored in Redis (single-use).
    EIMZO_CHALLENGE_TTL_SECONDS: int = 300
    # DEV/DEMO ONLY — when true the gateway does NOT call the sidecar; it verifies a
    # synthetic PKCS#7 (a base64 JSON blob produced by the stub CAPIWS bridge) so the
    # full onboarding flow is exercisable without the UNICON artifact (e2e, dev stack
    # demo). MUST stay false in production (real O'zDSt verification via the sidecar).
    EIMZO_STUB: bool = False

    # ── Escrow provider callbacks (R6 / P7.b) ─────────────────────────────────
    # Shared secret the partner bank sends in `X-Escrow-Token` on every callback
    # to POST /api/v1/webhooks/escrow/{provider}.
    #
    # Empty default on purpose, and NOT a violation of "secrets have no defaults":
    # that rule exists so a misconfiguration fails fast at startup, but the escrow
    # rail is a RUNTIME setting (`escrow_mode`) that a startup validator cannot
    # see. Making this mandatory would force every deployment — including the
    # ones that never enable escrow — to invent a value. Same shape as
    # ESKIZ_EMAIL/ESKIZ_PASSWORD: conditionally required, validated at the point
    # of use. While it is empty the webhook route answers 404, so an unconfigured
    # deployment does not advertise the endpoint at all.
    ESCROW_WEBHOOK_SECRET: str = ""

    # ── Didox EDI partner API (R6 / P7.a) ─────────────────────────────────────
    # Uzbekistan's largest private EDI operator. We use it for two things: the
    # tax registry's own record of a company (`/v1/utils/info/{tin}`, which fills
    # the registration form and feeds the verification checks) and, later, the
    # legally significant document chain.
    #
    # Defaults to the TEST contour deliberately — production is a different host
    # AND a different token, so an accidental deploy hits the sandbox, not the
    # roaming centre.
    DIDOX_BASE_URL: str = "https://testapi3.didox.uz"
    # Integrator identity, sent as `Partner-Authorization` on every request.
    # Empty default for the same reason as ESCROW_WEBHOOK_SECRET above: the rail
    # is a RUNTIME setting (`didox_mode`, `gov_registry_mode`) that a startup
    # validator cannot see. Obtained offline from the account manager. It is a
    # server-side secret and must NEVER reach a browser.
    DIDOX_PARTNER_TOKEN: str = ""  # [SECRET] required only when the Didox rail is on
    # Optional platform service account. The lookup needs a per-user `user-key`
    # in production (the test contour does not ask for one), and a key can only
    # be minted for a company that already uses Didox — which a company
    # registering with us, by definition, may not. These credentials let the
    # backend mint ONE key for our own company and reuse it for read-only
    # lookups. Leave empty and the lookup simply degrades to unavailable in prod.
    DIDOX_SERVICE_TIN: str = ""
    DIDOX_SERVICE_PASSWORD: str = ""  # [SECRET] optional; password login has a lockout ladder
    # The commercial package, as contracted — 1,000,000 requests a month for
    # 250,000 UZS. Settings rather than constants because a renegotiated contract
    # should be a panel edit, not a deploy, and because these two numbers are the
    # entire basis of what /admin/analytics reports: printed here, they can be
    # checked against the invoice instead of taken on trust.
    #
    # They configure NOTHING at runtime — no request is refused when the quota is
    # exhausted, because Didox owns that decision and we would only be guessing at
    # their count. They are the denominator on a page, and nothing else.
    DIDOX_MONTHLY_QUOTA: int = Field(default=1_000_000, ge=0)
    DIDOX_MONTHLY_COST_UZS: int = Field(default=250_000, ge=0)

    # ── Runtime feature switches ──────────────────────────────────────────────
    # These used to live in the `app_settings` table with their defaults written
    # as Python literals in `settings_service._SPECS`, editable from a panel on
    # the dashboard's News page. That arrangement had one failure mode and it
    # cost real time: a switch nobody could find. A fresh database has no rows,
    # so every rail fell back to a default buried in code, and the symptom was a
    # 503 from a provider that was configured, reachable and working — the
    # Didox lookup on 31.08.2026. Finding the answer meant reading a service
    # module and then querying a table.
    #
    # So the switches live here now, in the one file that already declares the
    # deployment's contract, and `.env` at the repo root is the only place they
    # are set. `settings_service` still exists as the read-through, so call
    # sites are unchanged, but there is no database override and no admin write
    # path: what `.env` says IS what runs. Changing one needs a restart, which
    # is the honest cost of having exactly one source of truth.
    #
    # `Literal` does the closed-set validation the old `choices=` tuple did, and
    # `Field(ge=…, le=…)` the numeric bounds — both now fail at STARTUP rather
    # than at the write that never happens. Note the old `_coerce` silently
    # CLAMPED an out-of-range int; refusing to boot is better than running for a
    # month on a number nobody chose.

    # News engine (Phase 7–8).
    NEWS_AI_ENABLED: bool = True
    NEWS_REQUIRE_APPROVAL: bool = False
    REPORT_AUTO_PUBLISH: bool = False
    # Which parsing/prompts/news_extract_vN.md the classifier uses. Kept apart
    # from LLM_PROMPT_VERSION/REPORT_PROMPT_VERSION because it moves on its own.
    NEWS_PROMPT_VERSION: str = "v3"
    NEWS_REFRESH_INTERVAL_MINUTES: int = Field(default=60, ge=5, le=1440)

    # Company verification (R1).
    VERIFICATION_AUTO_APPROVE: bool = False

    # Contracts (R3). Days a contract may sit in `pending_counterparty` /
    # `pending_signatures` before `expire_stale_contracts` retires it.
    CONTRACT_PENDING_TTL_DAYS: int = Field(default=30, ge=1, le=365)

    # Escrow rail (P3/P7.b): `stub` = an operator confirms every movement,
    # `live` = the bank adapter drives it.
    ESCROW_MODE: Literal["stub", "live"] = "stub"

    # RFQ supplier push (P5) — notifying matched suppliers of a new buyer RFQ.
    RFQ_SUPPLIER_PUSH_ENABLED: bool = False
    RFQ_SUPPLIER_PUSH_TOP_N: int = Field(default=10, ge=1, le=100)
    RFQ_SUPPLIER_OFFER_MAX_AGE_DAYS: int = Field(default=90, ge=1, le=730)

    # Chemical compliance (P5).
    SUBSTANCE_AI_ENABLED: bool = True
    # Block publication of a regulated substance that has no licence/documents.
    # Ships OFF: turning it on rejects offers, so it is an operator's decision.
    DANGEROUS_CHECK_ENFORCED: bool = False
    # `stub` = our own `substances` table (there is no national registry),
    # `live` = a P7 adapter that does not exist yet and raises.
    CHEM_REGISTRY_MODE: Literal["stub", "live"] = "stub"

    # State registry (P7.c + P7.a). `stub` = manual operator snapshots,
    # `didox` = Didox's `/v1/utils/info/{tin}` (the channel ПЦД never became),
    # `live` = a ПЦД adapter that does not exist yet and raises.
    #
    # THIS is the switch that made the Didox lookup answer 503
    # `registry_not_configured` while the provider was perfectly healthy.
    GOV_REGISTRY_MODE: Literal["stub", "didox", "live"] = "stub"

    # Didox DOCUMENT rail (P7.a) — договор/ЭСФ/акт. Deliberately separate from
    # GOV_REGISTRY_MODE above: reading the tax registry is harmless, sending a
    # legally significant document is not. `stub` raises rather than pretending,
    # because a fabricated "signed" document is a false statement about a real
    # legal act.
    DIDOX_MODE: Literal["stub", "live"] = "stub"

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

    # ── Upstream provider hosts ───────────────────────────────────────────────
    # Base URLs of the third parties the built-in code adapters talk to. They
    # default to today's production hosts, so nothing changes unless a value is
    # set — but when one of them moves (or has to be pointed at a mirror, a
    # sandbox, or a local recording), that is now a line in `.env` rather than a
    # patched adapter. The no-code adapters are unaffected: their URLs are rows
    # in the `sources` table, which is already the right place for them.
    UZEX_BASE_URL: str = "https://uzex.uz"
    XARID_BASE_URL: str = "https://xarid-api-auction.uzex.uz"
    CBU_RATES_URL: str = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/"
    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz"

    # ── Timezone / display ────────────────────────────────────────────────────
    TZ_DISPLAY: str = "Asia/Tashkent"

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Runtime ───────────────────────────────────────────────────────────────
    # Deployment environment. `production` is the only value that changes
    # behaviour: it sets `Secure` on the staff refresh cookie, so the session
    # cookie is refused over plain HTTP.
    #
    # This was read straight from `os.environ` in `auth_service` at import time
    # and appeared in no contract, no validator and no `.env.example`. A
    # deployment that forgot it did not fail, or warn — it quietly issued staff
    # session cookies without `Secure`, which is exactly the kind of thing that
    # is only ever noticed by whoever is looking for it. Declared here it is
    # part of the env contract like everything else, and the Literal refuses a
    # typo (`prod`, `Production `) that would silently mean "not production".
    APP_ENV: Literal["development", "staging", "production"] = "development"

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

    @field_validator("VERIFICATION_ENC_KEY")
    @classmethod
    def _enc_key_min_length(cls, v: str) -> str:
        """Reject a verification encryption key shorter than 32 chars at startup.

        A short/blank key defeats the app-layer encryption of bank account numbers
        (§15). Fernet keys are 44-char urlsafe base64; the CI placeholder satisfies
        this. Fail fast rather than silently storing weakly-protected PII.
        """
        if len(v) < 32:
            raise ValueError("VERIFICATION_ENC_KEY must be at least 32 characters")
        return v

    @field_validator(
        "REQUEST_NOTIFY_CHAT_ID",
        "NOTIFY_TOPIC_BUYERS",
        "NOTIFY_TOPIC_SELLERS",
        "VERIFICATION_NOTIFY_CHAT_ID",
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

    @field_validator("OTP_DEV_CODE")
    @classmethod
    def _dev_otp_shape(cls, v: str) -> str:
        """Empty, or exactly the digits a real code has.

        A 5-digit "dev code" would never match a stored hash, and the symptom
        would read as a broken OTP flow rather than a typo in `.env`. The length
        is `otp_service.CODE_LENGTH`, which cannot be imported here (config must
        stay dependency-free) — a test asserts the two agree.
        """
        if not v:
            return v
        if len(v) != 6 or not v.isdigit():
            raise ValueError("OTP_DEV_CODE must be empty or exactly 6 digits (e.g. 000000)")
        return v

    @field_validator("OTP_RESEND_COOLDOWN_SECONDS", "OTP_TTL_SECONDS")
    @classmethod
    def _positive_seconds(cls, v: int) -> int:
        """At least one second — Redis refuses a non-positive TTL.

        `otp_service.request_code` passes these straight to `SET … EX`, and Redis
        answers `invalid expire time` for anything ≤ 0. The result is a 500 on
        every sign-in: the login is simply down, and nothing about the symptom
        points at a number in `.env`. Someone reaching for "no cooldown" writes
        `0` because it is the obvious way to say that, so this fails at startup
        instead — the same bargain the required secrets make.
        """
        if v < 1:
            raise ValueError("must be at least 1 second (Redis refuses a non-positive TTL)")
        return v

    @model_validator(mode="after")
    def _reject_fixed_otp_with_real_sms(self) -> Self:
        """Refuse a fixed OTP alongside a real SMS provider.

        `otp_service` would ignore the setting anyway (it requires the console
        driver), but ignoring it silently is the wrong answer: the operator asked
        for every real user's code to be the same six digits. That is either a
        `.env` copied from dev or a serious misunderstanding, and both deserve a
        boot failure rather than a stack that looks fine.
        """
        if self.OTP_DEV_CODE and self.SMS_PROVIDER != "console":
            raise ValueError(
                "OTP_DEV_CODE is a dev-only fixed OTP and cannot be combined with "
                f"SMS_PROVIDER={self.SMS_PROVIDER!r} — clear it, or use the console driver"
            )
        return self

    @model_validator(mode="after")
    def _reject_eimzo_stub_outside_debug(self) -> Self:
        """Refuse the dev E-IMZO verifier on anything that looks like production.

        `EIMZO_STUB` is not merely "synthetic" any more — it now also ACCEPTS a
        real PKCS#7 after reading its certificate and confirming it covers our
        challenge, without checking the O'zDSt signature bytes, the trust chain
        or revocation (`integrations/eimzo/local_verify.py`). That is exactly
        what a developer needs and exactly what an attacker needs: anyone with a
        public certificate could wrap our challenge in a forged envelope and come
        out `identity_locked`.

        The setting was already documented «MUST stay false in production», which
        is a comment, not a guard. `DEBUG` is the one flag every production
        deployment already turns off, so pinning the two together makes the rule
        enforceable at boot instead of trusting a `.env` never to be copied.
        """
        if self.EIMZO_STUB and not self.DEBUG:
            raise ValueError(
                "EIMZO_STUB verifies signatures WITHOUT crypto and is dev-only; it "
                "cannot be combined with DEBUG=false — set EIMZO_STUB=false and run "
                "the e-imzo-server sidecar (EIMZO_SERVER_URL) for real verification"
            )
        return self

    @model_validator(mode="after")
    def _require_didox_token_when_a_rail_is_on(self) -> Self:
        """Refuse a Didox rail switched on without the partner token.

        Both rails degrade politely when the token is missing — the registry
        lookup answers `registry_unavailable`, the document rail
        `didox_unavailable`. That is right when the provider is genuinely down
        and wrong here: the operator asked for Didox and got a 503 that blames
        Didox for an empty line in `.env`. Same bargain as ESKIZ_EMAIL: the
        credential is conditionally required, so it is checked the moment the
        condition is visible, which is now.

        Nothing fires on the shipped defaults (both rails `stub`), so a
        deployment that never enables Didox needs no value.
        """
        rails = [
            name
            for name, on in (
                ("GOV_REGISTRY_MODE=didox", self.GOV_REGISTRY_MODE == "didox"),
                ("DIDOX_MODE=live", self.DIDOX_MODE == "live"),
            )
            if on
        ]
        if rails and not self.DIDOX_PARTNER_TOKEN:
            raise ValueError(
                f"DIDOX_PARTNER_TOKEN is required when {' and '.join(rails)} — "
                "set it in .env or put the rail back to its default"
            )
        return self

    @model_validator(mode="after")
    def _require_openai_key_for_gpt(self) -> Self:
        """Refuse a GPT model selected without an OpenAI key.

        Same bargain as the two validators around this one: the credential is
        conditionally required, so it is checked the moment the condition is
        visible. It matters more here than the wording suggests, because every
        LLM feature DEGRADES rather than errors — a GPT model with no key would
        show up as news that classifies badly and a report that quietly falls
        back to rule-based summaries, with nothing naming the empty line in
        `.env` that caused it.

        It fires at the write as well as at boot, for free: `settings_service`
        validates an override by building a candidate `Settings`, so selecting a
        GPT model in the panel with no key saved is refused there too.
        """
        from app.services.llm_clients import OPENAI, provider_of  # noqa: PLC0415

        gpt = [
            f"{name}={value}"
            for name, value in (
                ("LLM_EXTRACT_MODEL", self.LLM_EXTRACT_MODEL),
                ("LLM_REPORT_MODEL", self.LLM_REPORT_MODEL),
            )
            if provider_of(value) == OPENAI
        ]
        if gpt and not self.OPENAI_API_KEY:
            raise ValueError(
                f"OPENAI_API_KEY is required when {' and '.join(gpt)} — "
                "set the key first, or choose a Claude model"
            )
        return self

    @model_validator(mode="after")
    def _require_escrow_secret_when_live(self) -> Self:
        """`ESCROW_MODE=live` with no callback secret is a one-way rail.

        The webhook route answers 404 while `ESCROW_WEBHOOK_SECRET` is empty, so
        a `live` escrow would send instructions to the bank and be structurally
        unable to hear the answer. Payments would sit `pending` forever with
        nothing in the logs to say why.
        """
        if self.ESCROW_MODE == "live" and not self.ESCROW_WEBHOOK_SECRET:
            raise ValueError(
                "ESCROW_WEBHOOK_SECRET is required when ESCROW_MODE=live — without it the "
                "bank's callback endpoint answers 404 and no payment can ever settle"
            )
        return self

    @model_validator(mode="after")
    def _require_eskiz_creds(self) -> Self:
        """Require Eskiz credentials only when SMS_PROVIDER=eskiz.

        The console driver (dev/CI default) needs no credentials; the real Eskiz
        driver fails fast at startup if either credential is missing rather than at
        the first OTP send.
        """
        if self.SMS_PROVIDER == "eskiz" and not (self.ESKIZ_EMAIL and self.ESKIZ_PASSWORD):
            raise ValueError("ESKIZ_EMAIL and ESKIZ_PASSWORD are required when SMS_PROVIDER=eskiz")
        return self


# Single module-level accessor — import `settings` everywhere, do not call Settings() twice.
# BaseSettings reads required fields from environment; mypy can't see that.
settings = Settings()  # type: ignore[call-arg]
