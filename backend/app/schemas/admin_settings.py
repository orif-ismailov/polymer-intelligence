"""Schemas for the admin settings + news-ops panel (Phase 8d)."""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class SettingItem(BaseModel):
    """One runtime switch: what is running, what `.env` says, and who changed it.

    Both values, always, side by side. That pairing is the point of the whole
    screen — a panel showing only the effective value would answer "what is it?"
    but not "why is it that, and what happens if I put it back?", which is the
    question that cost a day on 31.08.2026. `env_var` names the line in `.env`
    for the same reason.

    `value` covers bool, float, str and int switches. Order matters: bool before
    int so True/False don't validate as 1/0, and int before float so a whole
    number does not come back as `1.0`. Secrets arrive here already masked (see
    `settings_service.mask`) — the real value never leaves the server.
    """

    key: str
    label: str
    #: Which section of the panel this belongs in (news, didox, notify, …).
    group: str
    #: The value this deployment is actually running.
    value: bool | int | float | str | None
    #: What `.env` says, i.e. what `Reset` would restore.
    env_value: bool | int | float | str | None
    #: The `Settings` field / `.env` key that sets this switch.
    env_var: str
    #: True when an override row exists, i.e. `value` and `env_value` may differ.
    overridden: bool
    overridden_by: str | None
    overridden_at: datetime.datetime | None
    #: False → env-only, shown read-only. Changing it needs `.env` and a restart.
    editable: bool
    #: True → a credential: masked here, and writable only by an administrator.
    sensitive: bool
    #: Non-empty → the UI must make the operator confirm, and this says why.
    confirm: str
    #: How to render the control: bool | int | float | choice | str.
    kind: str
    #: The permitted values when `kind == "choice"`, else empty.
    choices: list[str]


class PromptVersionItem(BaseModel):
    """One version of the news prompt, shipped or authored."""

    version: str
    #: True → this text came out of the image; there is no row and no author.
    shipped: bool
    #: True → this is the version the pipeline is running right now.
    active: bool
    created_by: str | None
    created_at: datetime.datetime | None
    note: str | None
    #: Characters. Shown because the prompt is billed on every article, so its
    #: length is a recurring cost that is otherwise invisible at the moment of
    #: pasting.
    size: int


class NewsPromptOut(BaseModel):
    """The prompt editor's whole state."""

    active_version: str
    #: The active version's text — from the authored row if there is one, else
    #: from the file that shipped.
    body: str
    #: True → the active version is a shipped file, so editing it will create a
    #: new version rather than change anything that exists.
    shipped: bool
    #: What a save would be called.
    next_version: str
    max_chars: int
    versions: list[PromptVersionItem]


class NewsPromptCreate(BaseModel):
    """A new version of the news prompt."""

    body: str
    note: str | None = None


class NewsPromptTry(BaseModel):
    """A dry run: classify one already-collected article with an unsaved prompt."""

    body: str
    #: Which article to try it on. None → the most recent news item collected.
    raw_item_id: int | None = None


class NewsPromptTryOut(BaseModel):
    """What the trial produced. Nothing about it is persisted."""

    raw_item_id: int
    #: The article's own text, so the operator can judge the answer against it.
    excerpt: str
    #: The parsed `NewsArticle`, as the classifier returned it.
    article: dict[str, object]
    tokens_in: int
    tokens_out: int
    latency_ms: float


class SettingUpdate(BaseModel):
    """A new value for one switch.

    Deliberately untyped (`object`): the switches span bool, int, float, str and
    nullable ints, and the only validator that may decide whether a value is
    acceptable is `Settings` itself — see `settings_service.validate`. A type
    here would be a second, weaker opinion about the same question, and the two
    would drift.
    """

    value: object


class NewsStats(BaseModel):
    """Admin dashboard news-ops snapshot."""

    total_sources: int
    active_sources: int
    failed_sources: int
    last_scan: datetime.datetime | None
    last_published_report: datetime.datetime | None
    pending_ai_analysis: int
    today_published_news: int
    ai_enabled: bool
    ai_status: str  # "on" | "off" | "error"
    ai_errors_recent: int = 0  # extractor errors in the last 30 min (currently-failing signal)
    ai_last_error: str | None = None
    budget_used_pct: float = 0.0


class PendingNewsItem(BaseModel):
    """A classified news article awaiting approval (dashboard review queue)."""

    id: int
    headline: str
    category: str | None = None
    importance: str | None = None
    summary: str | None = None
    country: str | None = None
    source_name: str | None = None
    published_at: str | None = None


class SourceGroup(BaseModel):
    """A named source group with its member counts (Phase 8f-2)."""

    group: str | None = None  # None = ungrouped
    total: int
    active: int


class SourceBrief(BaseModel):
    """Identity + group for a source (group-assignment UI)."""

    id: int
    name: str
    adapter: str
    country: str | None = None
    group_name: str | None = None
    is_enabled: bool


class SourceGroupUpdate(BaseModel):
    """Assign or clear a source's group."""

    group: str | None = None


class SourceActivity(BaseModel):
    """Per-source scan status + 24h yield for the news activity panel (Phase 8g)."""

    id: int
    name: str
    adapter: str
    group_name: str | None = None
    is_enabled: bool
    last_fetch_at: datetime.datetime | None = None
    last_success_at: datetime.datetime | None = None
    consecutive_failures: int
    raw_24h: int
    news_24h: int


class RunParserResult(BaseModel):
    """What a 'Run parser now' click enqueued, and which sources it will scan."""

    enqueued: list[str]
    sources: list[str]
    count: int
