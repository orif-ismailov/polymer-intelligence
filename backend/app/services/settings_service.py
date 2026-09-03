"""
Runtime settings — the env contract, with an override layer on top.

    effective value = the `app_settings` row, if one exists, else `.env`

`.env` at the repo root remains the complete contract and the default for every
switch here: `deploy/.env.example` documents each one, `Settings` validates them
at startup, and a deployment that never opens the admin panel runs exactly what
that file says. The `app_settings` table (migration 0045) holds only the
deliberate exceptions, one row per overridden key.

That ordering is the entire point, because a table of this name existed once
before and was removed. In that arrangement the DEFAULTS were Python literals in
this module and the table held the value; between the two there was nowhere to
read what a deployment was actually running. A fresh database has no rows, so
every rail resolved to something invisible — and on 31.08.2026 a healthy,
fully-credentialed Didox integration answered `503 registry_not_configured` on
every company lookup, which took a day to trace through a service module and
then a Postgres query.

What makes this version safe is that a missing row can no longer mean "some
default in code". It means the value printed in `.env.example`, and
`GET /admin/settings` shows both numbers side by side with the env var named, who
overrode it and when, and a reset action. An override is visible AS an override.

Three rules the rest of this module exists to keep:

- **`get()` never touches Postgres or Redis.** It is called inside open
  transactions — `verification/service.py` holds a `SELECT … FOR UPDATE` across
  it — and with `DB_POOL_SIZE=5` against uvicorn's 40-thread pool, a second
  connection checkout per call is a pool deadlock, not a slow path. Overrides
  reach a process through `refresh(db)`, which runs where a session already
  exists (`get_db`) or where none is open yet (Celery's `task_prerun`).
- **A write is validated by `Settings` itself**, by building a candidate model,
  so bounds, `Literal` sets and the cross-field rail-credential validators all
  fire — the same checks a boot would apply. Nothing here re-implements them.
- **The `settings` singleton is never assigned to.** `model_config` sets no
  `validate_assignment`, so `setattr` would bypass every validator in the file.
  Overrides live in this module's snapshot.

Adding a switch is a field on `Settings`, a `SettingSpec` here naming it, and
then `make env-sync` — which appends the `deploy/.env.example` line with the real
default and the right `[panel: X]` marker, leaving you one sentence of prose to
write. `tests/test_settings_env_source.py` fails if a spec names a field that
does not exist; `tests/test_env_contract_sync.py` fails if the contract drifts,
if a marker is stale, or if a documented value is one `Settings` would refuse.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, cast, get_args, get_origin

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.config import settings as _config
from app.core.crypto import decrypt_pii, encrypt_pii
from app.core.paths import PROMPTS_DIR
from app.models.app_settings import AppSetting
from app.models.staff import StaffUser

logger = logging.getLogger(__name__)

#: A setting value. `None` is legal — the notify chat ids are `int | None`, and
#: "unset" is a meaningful override distinct from "no override".
SettingValue = bool | str | int | float | None

#: Redis key holding a counter bumped on every write. A process compares it to
#: the generation its snapshot was loaded at; equal means nothing to do.
GENERATION_KEY = "settings:generation"

#: How long to ignore Redis after it fails a probe. Without this, an outage
#: costs every request `SIGNAL_TIMEOUT_SECONDS` of dead wait, forever.
REDIS_BACKOFF_SECONDS = 30.0

#: How stale a snapshot may get when Redis is unreachable and the generation
#: cannot be read. The fallback is time, not chance.
BLIND_RELOAD_SECONDS = 60.0

#: Models an operator may pick for the per-item extractor. A closed set rather
#: than free text because the failure of a typo is remote: `parse_news_item`
#: dead-letters on the Anthropic 404 and every following news item fails the
#: same way, while `substance_ai` swallows it and the seller simply sees a
#: missing feature. The live value is always offered too (see `allowed_values`),
#: so a deployment pinning something newer never sees a list without its own
#: value in it.
#: Cheapest-first within each vendor, because this list is read top-down by
#: somebody choosing. `llm_clients.provider_of` derives the vendor from the id,
#: so adding a model here is the whole of adding a model — there is no second
#: place naming which provider it belongs to.
EXTRACT_MODELS: tuple[str, ...] = (
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-opus-5",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-5-mini",
    "gpt-5",
)

#: Models an operator may pick for the daily/evening brief. A shorter list than
#: the extractor's: the report is two calls a day against a ~6.5k-token output,
#: so the cheap tiers that make sense per-article do not make sense here, and a
#: weak summary is the most visible thing this platform publishes.
REPORT_MODELS: tuple[str, ...] = (
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-opus-5",
    "gpt-4.1",
    "gpt-5",
)


class InvalidSetting(Exception):
    """A write was refused. The message is safe to show an operator.

    Safe means: it names the field and what was wrong with it, and it never
    carries a value from the candidate model. See `_safe_message`.
    """


@dataclass(frozen=True)
class SettingSpec:
    """One switch: its stable key, the env var that sets it, and how it behaves.

    `key` is the snake_case name every call site uses and is deliberately NOT
    derived from `env_var` — several keys predate this module and appear in
    tests, docs and planning notes, so they stay stable while the env var is free
    to be named for the `.env` file it lives in.
    """

    key: str
    env_var: str
    label: str
    group: str

    #: May an operator override this from the panel? Defaults to False so a new
    #: spec is env-only until somebody opts it in — a one-line diff a reviewer
    #: can see, rather than a default that quietly widens the write surface.
    overridable: bool = False

    #: Value is a credential: Fernet-encrypted at rest, masked on read, and
    #: writable only by an administrator regardless of the page grant.
    sensitive: bool = False

    #: Non-empty → the UI demands an explicit confirmation, and this is the
    #: sentence it shows. A reason rather than a bare flag, because "are you
    #: sure?" with no stated consequence is a click people learn to skip.
    confirm: str = ""

    #: Closed set for a field whose TYPE is free text. `Literal` fields derive
    #: their choices from the annotation and need nothing here.
    choices: tuple[str, ...] | None = field(default=None)


def _specs() -> tuple[SettingSpec, ...]:
    return (
        # ── News engine ───────────────────────────────────────────────────────
        SettingSpec(
            "news_ai_enabled",
            "NEWS_AI_ENABLED",
            "AI summaries in reports",
            "news",
            overridable=True,
        ),
        SettingSpec(
            "news_require_approval",
            "NEWS_REQUIRE_APPROVAL",
            "Require approval before news is published",
            "news",
            overridable=True,
        ),
        SettingSpec(
            "report_auto_publish",
            "REPORT_AUTO_PUBLISH",
            "Auto-publish generated reports",
            "news",
            overridable=True,
            confirm=(
                "Approved reports will post to the Telegram news channel without a "
                "human check. A published post cannot be recalled from subscribers."
            ),
        ),
        # ── AI provider ───────────────────────────────────────────────────────
        # Not filed under `news`, though the model used to be: this key and this
        # model drive the news classifier, the daily reports, buyer-request
        # analysis and the substance hint. Naming the group after one of the four
        # would misdescribe what changing them affects.
        SettingSpec(
            "anthropic_api_key",
            "ANTHROPIC_API_KEY",
            "Anthropic API key",
            "ai",
            overridable=True,
            sensitive=True,
        ),
        SettingSpec(
            "openai_api_key",
            "OPENAI_API_KEY",
            "OpenAI API key",
            "ai",
            overridable=True,
            sensitive=True,
        ),
        SettingSpec(
            "llm_extract_model",
            "LLM_EXTRACT_MODEL",
            "AI model for news and hints",
            "ai",
            overridable=True,
            choices=EXTRACT_MODELS,
        ),
        SettingSpec(
            "llm_report_model",
            "LLM_REPORT_MODEL",
            "AI model for reports",
            "ai",
            overridable=True,
            choices=REPORT_MODELS,
        ),
        SettingSpec(
            "news_prompt_version",
            "NEWS_PROMPT_VERSION",
            "News prompt version",
            "news",
            overridable=True,
        ),
        SettingSpec(
            "news_refresh_interval_minutes",
            "NEWS_REFRESH_INTERVAL_MINUTES",
            "News refresh interval (minutes)",
            "news",
            overridable=True,
        ),
        # ── Verification & contracts ──────────────────────────────────────────
        SettingSpec(
            "verification_auto_approve",
            "VERIFICATION_AUTO_APPROVE",
            "Auto-approve verification cases when all automated checks pass",
            "deals",
            overridable=True,
            confirm=(
                "This applies to cases ALREADY waiting: each one is approved the "
                "moment its last check finishes, recorded against no staff member, "
                "and grants the company its verified roles."
            ),
        ),
        SettingSpec(
            "contract_pending_ttl_days",
            "CONTRACT_PENDING_TTL_DAYS",
            "Days a contract may await the counterparty/signatures before it expires",
            "deals",
            overridable=True,
            confirm=(
                "Lowering this retires every pending contract already older than the "
                "new limit on the next nightly sweep."
            ),
        ),
        # ── Payments ──────────────────────────────────────────────────────────
        SettingSpec(
            "escrow_mode",
            "ESCROW_MODE",
            "Escrow rail: stub (an operator confirms movement) or live (bank adapter)",
            "deals",
            overridable=True,
            confirm=(
                "`live` hands payment instructions to the bank adapter. Movements it "
                "reports back are applied to real deals."
            ),
        ),
        # ── Sourcing ──────────────────────────────────────────────────────────
        SettingSpec(
            "rfq_supplier_push_enabled",
            "RFQ_SUPPLIER_PUSH_ENABLED",
            "Notify matching suppliers when a buyer publishes an RFQ",
            "sourcing",
            overridable=True,
        ),
        SettingSpec(
            "rfq_supplier_push_top_n",
            "RFQ_SUPPLIER_PUSH_TOP_N",
            "How many matched suppliers one RFQ may notify",
            "sourcing",
            overridable=True,
        ),
        SettingSpec(
            "rfq_supplier_offer_max_age_days",
            "RFQ_SUPPLIER_OFFER_MAX_AGE_DAYS",
            "How recent a supplier's listing must be to count as a match",
            "sourcing",
            overridable=True,
        ),
        # ── Chemical compliance ───────────────────────────────────────────────
        SettingSpec(
            "substance_ai_enabled",
            "SUBSTANCE_AI_ENABLED",
            "Offer an AI substance hint on the seller's offer form",
            "compliance",
            overridable=True,
        ),
        SettingSpec(
            "dangerous_check_enforced",
            "DANGEROUS_CHECK_ENFORCED",
            "Block publication of regulated substances without licence/documents",
            "compliance",
            overridable=True,
            confirm=(
                "Turning this OFF lets regulated substances be published with no "
                "licence on file, and offers published while it is off stay published."
            ),
        ),
        SettingSpec(
            "chem_registry_mode",
            "CHEM_REGISTRY_MODE",
            "Chemical registry: stub (our own substance table) or live (P7 adapter)",
            "compliance",
            overridable=True,
        ),
        # ── State registry ────────────────────────────────────────────────────
        SettingSpec(
            "gov_registry_mode",
            "GOV_REGISTRY_MODE",
            "State registry: stub (manual operator checks), didox (Didox lookup) or live (ПЦД)",
            "didox",
            overridable=True,
        ),
        # ── Didox EDI ─────────────────────────────────────────────────────────
        SettingSpec(
            "didox_mode",
            "DIDOX_MODE",
            "Didox document rail: stub (no documents leave the platform) or live",
            "didox",
            overridable=True,
            confirm=(
                "`live` sends legally significant documents (договор, ЭСФ, акт) to the "
                "tax authority through Didox. A filed document cannot be withdrawn here."
            ),
        ),
        SettingSpec(
            "didox_base_url",
            "DIDOX_BASE_URL",
            "Didox API host (test contour or the production roaming centre)",
            "didox",
            overridable=True,
        ),
        SettingSpec(
            "didox_partner_token",
            "DIDOX_PARTNER_TOKEN",
            "Didox partner token (integrator identity)",
            "didox",
            overridable=True,
            sensitive=True,
        ),
        SettingSpec(
            "didox_service_tin",
            "DIDOX_SERVICE_TIN",
            "Didox service-account ИНН (mints the read-only lookup key)",
            "didox",
            overridable=True,
        ),
        SettingSpec(
            "didox_service_password",
            "DIDOX_SERVICE_PASSWORD",
            "Didox service-account password",
            "didox",
            overridable=True,
            sensitive=True,
        ),
        # The contracted package. These change nothing at runtime — no request is
        # refused when the quota runs out, because Didox owns that count and we
        # would be guessing. They are what /admin/analytics divides by.
        SettingSpec(
            "didox_monthly_quota",
            "DIDOX_MONTHLY_QUOTA",
            "Didox requests included per month",
            "didox",
            overridable=True,
        ),
        SettingSpec(
            "didox_monthly_cost_uzs",
            "DIDOX_MONTHLY_COST_UZS",
            "Didox package price per month, UZS",
            "didox",
            overridable=True,
        ),
        # ── Telegram notification routing ─────────────────────────────────────
        SettingSpec(
            "request_notify_chat_id",
            "REQUEST_NOTIFY_CHAT_ID",
            "Team chat that receives new buyer requests",
            "notifications",
            overridable=True,
        ),
        SettingSpec(
            "notify_topic_buyers",
            "NOTIFY_TOPIC_BUYERS",
            "Forum topic for buyer-side notifications",
            "notifications",
            overridable=True,
        ),
        SettingSpec(
            "notify_topic_sellers",
            "NOTIFY_TOPIC_SELLERS",
            "Forum topic for seller-side notifications",
            "notifications",
            overridable=True,
        ),
        SettingSpec(
            "verification_notify_chat_id",
            "VERIFICATION_NOTIFY_CHAT_ID",
            "Team chat that receives verification cases",
            "notifications",
            overridable=True,
        ),
        SettingSpec(
            "news_channel_id",
            "NEWS_CHANNEL_ID",
            "Telegram channel approved reports are published to",
            "notifications",
            overridable=True,
        ),
        # ── Ingest HTTP tunables ──────────────────────────────────────────────
        SettingSpec(
            "ingest_http_timeout_seconds",
            "INGEST_HTTP_TIMEOUT_SECONDS",
            "How long a collector waits for one upstream response (seconds)",
            "ingest",
            overridable=True,
        ),
        SettingSpec(
            "ingest_http_retries",
            "INGEST_HTTP_RETRIES",
            "How many times a collector retries a failed fetch",
            "ingest",
            overridable=True,
        ),
        SettingSpec(
            "ingest_user_agent",
            "INGEST_USER_AGENT",
            "User-Agent the collectors identify themselves with",
            "ingest",
            overridable=True,
        ),
        SettingSpec(
            "ingest_per_host_delay_seconds",
            "INGEST_PER_HOST_DELAY_SECONDS",
            "Politeness delay between two fetches of the same host (seconds)",
            "ingest",
            overridable=True,
        ),
    )


#: Public because the admin listing, the write path and their tests all walk it.
SPECS: dict[str, SettingSpec] = {s.key: s for s in _specs()}


# ── Process-local override snapshot ───────────────────────────────────────────
#
# Plain module state, deliberately. It is read on the hottest path in the app
# (`gov_registry.current_mode()` runs several times per company lookup), so the
# read has to be a dict lookup and nothing else.

_overrides: dict[str, SettingValue] = {}

#: Operator-authored prompt bodies, `{(family, version): body}`.
#:
#: They ride in this snapshot rather than being read when needed, because the
#: place that needs them is `parsing.news_extractor.load_news_prompt`, called from
#: inside `parse_news_item`'s open transaction — so a database read there is the
#: same nested-checkout deadlock `get()` is forbidden from causing. `refresh(db)`
#: already runs on a session the caller owns, at the two moments in a process's
#: life when nothing else is open on it; the bodies come along for that ride.
#:
#: Safe to cache without expiry because `prompt_versions` is append-only: a
#: version's text never changes, so a body held here can be out of date only by
#: not existing yet, which the generation counter fixes on the next refresh.
_prompts: dict[tuple[str, str], str] = {}

_generation: int | None = None
_redis_quiet_until: float = 0.0
_blind_reload_after: float = 0.0

#: Tests set this False. `get()` is pure either way — this only governs whether
#: `refresh()` reaches for Redis and Postgres, which the unit suite has neither
#: of. Production code never touches it.
AUTO_REFRESH: bool = True


# ── Reading ───────────────────────────────────────────────────────────────────


def get(key: str) -> SettingValue:
    """Resolve one switch: the override if this process has one, else `.env`.

    Pure in-memory, by rule. Every call site is inside an open transaction or a
    hot request path; see the module docstring for what a database read here
    would cost.

    Raises `KeyError` for an unknown key rather than returning a falsy default,
    so a mistyped switch fails loudly instead of reading as "off".
    """
    spec = SPECS.get(key)
    if spec is None:
        raise KeyError(key)
    if key in _overrides:
        return _overrides[key]
    return cast(SettingValue, getattr(_config, spec.env_var))


def env_value(key: str) -> SettingValue:
    """What `.env` says for this key, ignoring any override."""
    return cast(SettingValue, getattr(_config, SPECS[key].env_var))


# ── Named accessors ───────────────────────────────────────────────────────────
#
# `get("request_notify_chat_id")` returns `SettingValue`, which every caller then
# has to narrow. These give the four notification targets a type and a name, and
# fold in the one piece of routing logic that was previously copy-pasted: the
# verification fallback existed verbatim in five modules, so "which chat gets a
# verification card" had five places it could be answered differently.


def notify_chat_id() -> int | None:
    """The team chat that receives buyer-side notifications. None → disabled."""
    return cast("int | None", get("request_notify_chat_id"))


def verification_chat_id() -> int | None:
    """Verification cards go to their own chat, falling back to the request group."""
    return cast("int | None", get("verification_notify_chat_id")) or notify_chat_id()


def buyers_topic() -> int | None:
    """Forum topic for buyer-side posts. None → the group's General topic."""
    return cast("int | None", get("notify_topic_buyers"))


def sellers_topic() -> int | None:
    """Forum topic for seller-side posts. None → the group's General topic."""
    return cast("int | None", get("notify_topic_sellers"))


def news_channel_id() -> str:
    """Telegram channel approved reports publish to. Empty → publishing is a no-op."""
    return str(get("news_channel_id") or "")


def allowed_values(key: str) -> tuple[str, ...] | None:
    """The closed set of values this key accepts, or None if it is free.

    Three sources, in order: the spec's explicit `choices`, the shipped prompt
    files for `news_prompt_version`, and the `Literal` args of the `Settings`
    field. The last is derived rather than duplicated — a rail that grows a
    fourth mode gets it in the panel with no edit here.

    The live env value is always appended when missing. A panel that offers a
    list not containing the value currently running is worse than no list: the
    operator's only way to keep what they have is to not touch the control.
    """
    spec = SPECS[key]
    values: tuple[str, ...] | None = spec.choices
    if key == "news_prompt_version":
        values = _news_prompt_versions()
    if values is None:
        annotation = Settings.model_fields[spec.env_var].annotation
        if get_origin(annotation) is Literal:
            values = tuple(str(arg) for arg in get_args(annotation))
    if values is None:
        return None
    live = env_value(key)
    if isinstance(live, str) and live and live not in values:
        values = (*values, live)
    return values


def _news_prompt_versions() -> tuple[str, ...]:
    """Every news prompt version this deployment can actually load.

    Two sources, and the list is their UNION: the `news_extract_v*.md` files
    baked into the image, plus the versions an operator authored from the panel
    (which live in this process's snapshot, so this needs no session).

    Both halves are enumerated rather than assumed, because the hazard is a
    version that is NAMED somewhere and absent everywhere —
    `news_extractor.load_news_prompt` used to answer `""` for one and cache it,
    classifying every article with no system prompt at all while journalling a
    version that had never been loaded. That is fixed at the loader; this stops
    an operator from asking for it in the first place.
    """
    shipped = {
        path.stem.removeprefix("news_extract_")
        for path in PROMPTS_DIR.glob("news_extract_v*.md")
    }
    authored = {version for family, version in _prompts if family == "news_extract"}
    return tuple(sorted(shipped | authored, key=_version_sort_key))


def _version_sort_key(version: str) -> tuple[int, str]:
    """Order `v2` before `v10`. Anything unparseable sorts last, by name."""
    digits = version[1:] if version.startswith("v") else version
    return (int(digits), "") if digits.isdigit() else (1 << 30, version)


def get_int(key: str) -> int:
    """An integer switch, narrowed.

    `SettingValue` is a union because the catalog spans bools, strings, floats
    and nullable ints; the call sites that want a count or a duration should not
    each have to re-establish that theirs is an int. Raises rather than
    defaulting, for the reason `get` raises on an unknown key: a switch that
    silently reads as zero is the failure this module exists to prevent.
    """
    value = get(key)
    if value is None or isinstance(value, str) and not value.strip():
        raise TypeError(f"{key} has no numeric value")
    return int(value)


def get_float(key: str) -> float:
    """A float switch, narrowed. See `get_int`."""
    value = get(key)
    if value is None or isinstance(value, str) and not value.strip():
        raise TypeError(f"{key} has no numeric value")
    return float(value)


def get_str(key: str) -> str:
    """A string switch, narrowed. `None` renders as empty — for the settings
    that are `str` in `Settings`, unset and empty are the same state."""
    value = get(key)
    return "" if value is None else str(value)


def get_bool(key: str) -> bool:
    """A boolean switch, narrowed."""
    return bool(get(key))


def kind(key: str) -> str:
    """How the panel should render this key: bool | int | float | choice | str."""
    if allowed_values(key) is not None:
        return "choice"
    annotation = Settings.model_fields[SPECS[key].env_var].annotation
    args = get_args(annotation)  # unwraps `int | None`
    types: set[object] = {arg for arg in args if isinstance(arg, type)} or {annotation}
    if bool in types:
        return "bool"
    if int in types:
        return "int"
    if float in types:
        return "float"
    return "str"


def mask(value: SettingValue) -> str:
    """Render a credential for display: never the value, always its shape.

    An empty secret renders as empty rather than as dots — "not set" and "set to
    something I cannot show you" are different facts about a deployment, and the
    panel exists to tell them apart.
    """
    text = "" if value is None else str(value)
    if not text:
        return ""
    return f"••••{text[-4:]}" if len(text) > 4 else "••••"


def get_all(db: Session) -> list[dict[str, object]]:
    """Every switch, resolved against the TABLE rather than this process's cache.

    Reading the rows directly is what makes the panel honest. A snapshot can be
    a refresh behind; the table is what a restart would load and what every
    other process is converging on, so it is the thing worth showing.
    """
    stored: dict[str, tuple[AppSetting, str | None]] = {
        row.AppSetting.key: (row.AppSetting, row.full_name)
        for row in db.execute(
            select(AppSetting, StaffUser.full_name).outerjoin(
                StaffUser, StaffUser.id == AppSetting.updated_by
            )
        ).all()
    }

    items: list[dict[str, object]] = []
    for spec in SPECS.values():
        env = env_value(spec.key)
        row = stored.get(spec.key)
        overridden = row is not None and spec.overridable
        value = _decode(row[0]) if (overridden and row is not None) else env
        items.append(
            {
                "key": spec.key,
                "label": spec.label,
                "group": spec.group,
                "env_var": spec.env_var,
                "value": mask(value) if spec.sensitive else value,
                "env_value": mask(env) if spec.sensitive else env,
                "overridden": overridden,
                "overridden_by": row[1] if (overridden and row is not None) else None,
                "overridden_at": row[0].updated_at if (overridden and row is not None) else None,
                "editable": spec.overridable,
                "sensitive": spec.sensitive,
                "confirm": spec.confirm,
                "kind": kind(spec.key),
                "choices": list(allowed_values(spec.key) or ()),
            }
        )
    return items


def _decode(row: AppSetting) -> SettingValue:
    """One stored row → its value, decrypting if the ROW says it is a secret."""
    if row.is_secret:
        return decrypt_pii(str(row.value).encode("utf-8"))
    return cast(SettingValue, row.value)


# ── Propagation ───────────────────────────────────────────────────────────────


def refresh(db: Session, *, force: bool = False) -> None:
    """Bring this process's snapshot up to date, cheaply, on the caller's session.

    Called from `get_db()` (on the session the request already holds, before the
    handler runs) and from Celery's `task_prerun` (where no transaction is open
    yet). Both are the only two moments in a process's life when reading the
    table costs nothing extra.

    Every failure is swallowed. A deployment whose `app_settings` table is
    missing — the TestClient-built app, a database mid-migration — must serve the
    env contract, not 500. That is also why the rollback below matters: a failed
    SELECT poisons the caller's transaction, and the caller is about to run a
    request on it.
    """
    if not AUTO_REFRESH:
        return
    now = time.monotonic()

    if not force:
        generation = _read_generation(now)
        if generation is not None:
            # `!=`, never `>`. A FLUSHALL makes the next INCR return 1, and a
            # process holding 7 would then treat the reset counter as old news
            # and go permanently stale.
            if generation == _generation:
                return
        elif _generation is not None and now < _blind_reload_after:
            # Redis is unreachable and the snapshot is not old enough to be
            # worth a blind read. Serve what we have.
            return

    _reload(db, now)


def _read_generation(now: float) -> int | None:
    """The current generation counter, or None if Redis could not be asked."""
    global _redis_quiet_until
    if now < _redis_quiet_until:
        return None
    try:
        from app.core.redis import signal_client  # noqa: PLC0415 — avoids an import cycle

        raw = signal_client().get(GENERATION_KEY)
        return int(raw) if raw else 0
    except Exception:  # noqa: BLE001 — any Redis failure means "ask again later"
        _redis_quiet_until = now + REDIS_BACKOFF_SECONDS
        logger.warning("settings.generation_unavailable", exc_info=True)
        return None


def _reload(db: Session, now: float) -> None:
    """Replace the snapshot from the table, and fire the invalidation hooks."""
    global _overrides, _prompts, _generation, _blind_reload_after
    try:
        rows = db.execute(select(AppSetting)).scalars().all()
        prompts = _load_prompt_bodies(db)
    except Exception:  # noqa: BLE001 — an absent table must not break a request
        db.rollback()
        _blind_reload_after = now + BLIND_RELOAD_SECONDS
        logger.warning("settings.overrides_unreadable", exc_info=True)
        return
    _prompts = prompts

    fresh: dict[str, SettingValue] = {}
    for row in rows:
        spec = SPECS.get(row.key)
        # A key dropped from the catalog, or one whose `overridable` opt-in was
        # withdrawn, stops applying without needing the row deleted first.
        if spec is None or not spec.overridable:
            continue
        try:
            fresh[row.key] = _decode(row)
        except Exception:  # noqa: BLE001 — a key rotation must not take the app down
            logger.error("settings.override_undecodable", extra={"key": row.key})

    previous, _overrides = _overrides, fresh
    _blind_reload_after = now + BLIND_RELOAD_SECONDS
    _generation = _read_generation(now) or 0

    changed = {k for k in set(previous) | set(fresh) if previous.get(k) != fresh.get(k)}
    if changed:
        _invalidate(changed)


def _load_prompt_bodies(db: Session) -> dict[tuple[str, str], str]:
    """Every authored prompt body, on the caller's session.

    Loaded together with the overrides so a process makes ONE trip for
    everything an operator can author. Lazily imported: `prompt_service` reads
    this module, and importing it here at module scope would be a cycle.
    """
    from app.services import prompt_service  # noqa: PLC0415

    return prompt_service.stored_bodies(db)


def prompt_body(family: str, version: str) -> str | None:
    """One authored prompt body from this process's snapshot, or None.

    Pure in-memory, by the same rule as `get()`. `None` means "not authored
    here", which is the caller's cue to fall back to the file that shipped —
    NOT an error and NOT an empty prompt. `parsing.news_extractor` makes that
    distinction; an empty system prompt is valid and silent, so nothing in this
    path may ever answer `""` for "I could not find it".
    """
    return _prompts.get((family, version))


def bump_generation() -> None:
    """Tell every other process its snapshot is stale.

    Best-effort: if Redis is down the others fall back to `BLIND_RELOAD_SECONDS`,
    which is slower but not wrong. A write must not fail because the fan-out did.
    """
    try:
        from app.core.redis import signal_client  # noqa: PLC0415

        signal_client().incr(GENERATION_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("settings.generation_bump_failed", exc_info=True)


def publish(db: Session, changed: set[str]) -> None:
    """Announce a committed write. Call this AFTER the transaction commits.

    Three things, in order: tell the other processes their snapshot is stale,
    bring this one up to date so the operator's next read reflects their own
    write, and run the side effects that belong to the WRITER alone (as opposed
    to `_invalidate`, which every process runs on reload).
    """
    bump_generation()
    refresh(db, force=True)
    _invalidate_shared(changed)


def _invalidate_shared(changed: set[str]) -> None:
    """Global side effects of a write — shared state, so exactly one process runs them."""
    if changed & {"didox_service_tin", "didox_service_password"}:
        try:
            from app.integrations.didox.auth import clear_cooldown  # noqa: PLC0415

            clear_cooldown()
        except Exception:  # noqa: BLE001
            logger.warning("settings.didox_cooldown_clear_failed", exc_info=True)


def _invalidate(changed: set[str]) -> None:
    """Drop the process-local caches that would otherwise mask a changed value.

    A switch whose new value is hidden behind a module-level cache is the
    invisible default wearing a different hat, so this runs in EVERY process on
    reload — not just in the one that took the write.
    """
    # Nothing to clear for `news_prompt_version` any more, and that is the point.
    # The loader used to cache the RESOLVED prompt keyed on the version string, so
    # a switch had to be chased with a `cache_clear()` in every process. It now
    # caches only the shipped FILE — which cannot change under a running process —
    # and reads authored bodies straight from the snapshot this reload just
    # replaced. A cache that cannot go stale needs no invalidation hook.
    if changed & {"didox_base_url", "didox_partner_token"}:
        try:
            from app.integrations.didox.client import reset_didox_client  # noqa: PLC0415

            reset_didox_client()
        except Exception:  # noqa: BLE001
            logger.warning("settings.didox_client_reset_failed", exc_info=True)

    if changed & {"anthropic_api_key", "openai_api_key"}:
        # Five modules hold LLM clients built at import with the keys baked in.
        # Without this, a key corrected in the panel would go on failing in every
        # worker until somebody restarted them — the provider looking broken
        # while the configuration looked right.
        try:
            from app.services import llm_clients  # noqa: PLC0415

            llm_clients.reset()
        except Exception:  # noqa: BLE001
            logger.warning("settings.llm_client_reset_failed", exc_info=True)


# ── Writing ───────────────────────────────────────────────────────────────────


def set_override(
    db: Session, key: str, value: object, staff_user_id: int | None
) -> SettingValue:
    """Override one switch. Returns the canonical value that was stored.

    Flushes without committing, like `audit_service.write_audit` — the caller
    owns the transaction so the override and its audit row land together or not
    at all. After the commit, the caller calls `bump_generation()`.
    """
    spec = _overridable(key)
    canonical = validate(key, value)
    _verify_with_provider(key, canonical)

    stored: object = (
        encrypt_pii("" if canonical is None else str(canonical)).decode("utf-8")
        if spec.sensitive
        else canonical
    )
    db.execute(
        pg_insert(AppSetting)
        .values(
            key=key,
            value=stored,
            is_secret=spec.sensitive,
            updated_by=staff_user_id,
        )
        .on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={
                "value": stored,
                "is_secret": spec.sensitive,
                "updated_by": staff_user_id,
                "updated_at": func.now(),
            },
        )
    )
    return canonical


def clear_override(db: Session, key: str) -> None:
    """Delete the override, returning the switch to whatever `.env` says."""
    _overridable(key)
    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)


def _verify_with_provider(key: str, value: SettingValue) -> None:
    """Ask the provider whether a credential works, before storing it.

    Only the two LLM keys do this, and only because of what they fail like. They
    drive the news classifier, the daily reports, buyer-request analysis and the
    substance hint, and every one of those DEGRADES on an LLM failure rather than
    erroring — the news classifies badly, the report falls back to a rule-based
    summary. A typo would therefore be expensive and silent, and the operator's
    next signal would be somebody noticing the news had got worse.

    The check reads the models endpoint and spends no tokens. Refusing a key we
    could not verify means a provider outage blocks a rotation; that is a wait,
    where storing an unverified key is a quiet outage of our own. The key already
    in use keeps working either way.

    Deliberately NOT generalised to the other credentials. The Didox token is
    validated by the rail that needs it (`_require_didox_token_when_a_rail_is_on`)
    and its provider has a lockout ladder that punishes probing; the escrow
    secret is checked by a bank we cannot call. Two credentials, one reason.
    """
    from app.services import llm_clients  # noqa: PLC0415 — avoids an import cycle

    providers = {
        "anthropic_api_key": llm_clients.ANTHROPIC,
        "openai_api_key": llm_clients.OPENAI,
    }
    provider = providers.get(key)
    if provider is None:
        return

    try:
        llm_clients.verify(str(value or ""), provider)
    except llm_clients.KeyRejected as exc:
        raise InvalidSetting(str(exc)) from exc


def _overridable(key: str) -> SettingSpec:
    spec = SPECS.get(key)
    if spec is None:
        raise KeyError(key)
    if not spec.overridable:
        raise InvalidSetting(f"{spec.env_var} can only be changed in .env")
    return spec


def validate(key: str, value: object) -> SettingValue:
    """Run a candidate value through `Settings` and return the canonical form.

    The whole model is validated, not just the one field, so `Field(ge=…)`
    bounds, the `Literal` closed sets and the cross-field `@model_validator`s all
    fire — including `_require_didox_token_when_a_rail_is_on` and
    `_require_escrow_secret_when_live`. That last pair is the real prize: setting
    `gov_registry_mode=didox` with no token is now refused here, naming the
    token, instead of becoming a 503 that blames Didox.

    The candidate layers the OTHER live overrides on top of `.env`, or setting a
    token and then a mode in two requests would fail on the second — the
    validator would be checking the mode against an env file that has no token.

    Returns the value pydantic parsed, so what we store is what a boot from the
    same string would produce.
    """
    spec = SPECS[key]

    allowed = allowed_values(key)
    if allowed is not None and str(value) not in allowed:
        raise InvalidSetting(f"must be one of: {', '.join(allowed)}")

    candidate: dict[str, object] = dict(_config.model_dump())
    for other_key, other_value in _overrides.items():
        candidate[SPECS[other_key].env_var] = other_value
    candidate[spec.env_var] = value

    try:
        validated = Settings.model_validate(candidate)
    except Exception as exc:  # noqa: BLE001 — narrowed by _safe_message
        raise InvalidSetting(_safe_message(exc, spec.env_var)) from exc
    return cast(SettingValue, getattr(validated, spec.env_var))


def _safe_message(exc: Exception, env_var: str) -> str:
    """A rejection an operator can act on, carrying no secret.

    `ValidationError.errors()` includes `input_value` for every error, and the
    dict we just validated holds `JWT_SECRET`, `VERIFICATION_ENC_KEY`,
    `DIDOX_PARTNER_TOKEN`, `S3_SECRET_KEY` and `TG_SESSION_STRING`. So the whole
    error list never crosses the wire: only `msg`, and only for errors about the
    field being written or about the model as a whole. The model-level messages
    are our own validators' text, which quotes no credential.
    """
    errors = getattr(exc, "errors", None)
    if errors is None:
        return "Value rejected by configuration validation."
    messages: list[str] = []
    for err in errors(include_url=False, include_input=False, include_context=False):
        loc = err.get("loc") or ()
        if not loc or env_var in loc:
            messages.append(str(err.get("msg", "")).removeprefix("Value error, "))
    if not messages:
        return "Value rejected by configuration validation."
    return "; ".join(dict.fromkeys(messages))


# ── Test seam ─────────────────────────────────────────────────────────────────
#
# `conftest.set_switch` writes through here rather than assigning to the
# `settings` singleton. Going through the real precedence path is the point: a
# helper that set the env layer would be silently shadowed by an override in any
# test that made one, and would prove nothing about the code that ships.


def seed_overrides(values: dict[str, SettingValue]) -> None:
    """Replace the in-memory snapshot. Tests only — touches no Redis, no DB."""
    global _overrides
    _overrides = dict(values)


def clear_snapshot() -> None:
    """Forget every override, prompt body and the generation. Tests only."""
    global _overrides, _prompts, _generation, _redis_quiet_until, _blind_reload_after
    _overrides = {}
    _prompts = {}
    _generation = None
    _redis_quiet_until = 0.0
    _blind_reload_after = 0.0


def seed_prompts(bodies: dict[tuple[str, str], str]) -> None:
    """Put authored prompt bodies in the snapshot. Tests only — no Redis, no DB."""
    global _prompts
    _prompts = dict(bodies)


def current_overrides() -> dict[str, SettingValue]:
    """A copy of the snapshot, for assertions and for the write path's layering."""
    return dict(_overrides)
