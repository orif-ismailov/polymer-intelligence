"""
Response shapes for `/admin/analytics`.

Every block carries `has_data`, and that is not decoration. A fresh deployment
and a broken one both produce zeros, and a zero rendered as a fact reads as "we
spent nothing" when it means "nothing has run yet" — so the flag is what lets the
page draw an empty state instead of a confident 0.
"""

from __future__ import annotations

from pydantic import BaseModel


class DidoxOperationStat(BaseModel):
    """One Didox endpoint's traffic this month."""

    operation: str
    calls: int
    ok: int
    failed: int
    p95_latency_ms: int | None


class DayCount(BaseModel):
    day: str
    calls: int


class FailureCount(BaseModel):
    error: str
    calls: int


class ProviderHealth(BaseModel):
    provider: str
    calls: int
    ok: int
    success_pct: float
    p95_latency_ms: int | None


class DidoxAnalytics(BaseModel):
    """This month's package consumption, in the operator's calendar month."""

    month_start: str
    days_in_month: int
    days_elapsed: int
    quota: int
    cost_uzs: int
    uzs_per_call: float
    #: Calls that actually reached Didox. Excludes `not_sent`.
    calls: int
    ok: int
    failed: int
    #: Refused by our own circuit breaker before any request left the process, so
    #: they cost no quota — reported apart from `calls` rather than folded in.
    not_sent: int
    projected: int
    #: Where usage would be today if the package were spent evenly. The meter's
    #: marker; without it a mid-month number cannot be read as good or bad.
    pace: int
    over_projection: bool
    spent_uzs: float
    by_operation: list[DidoxOperationStat]
    by_day: list[DayCount]
    failures: list[FailureCount]
    health: list[ProviderHealth]
    has_data: bool


class AiPurposeStat(BaseModel):
    purpose: str
    calls: int
    tokens_in: int
    tokens_out: int
    #: NULL by purpose: a purpose can span several models, and cost is per model.
    #: The by-model table is the exact one; this would be a guess dressed as a figure.
    est_cost_usd: float | None


class AiModelStat(BaseModel):
    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    est_cost_usd: float | None


class AiDayTokens(BaseModel):
    day: str
    purpose: str
    tokens: int


class AiDegradation(BaseModel):
    """Where the AI quietly did not work — every path here is silent by design."""

    errors: int
    fallbacks: int
    deferred: int
    rule_based_reports: int
    last_error: str | None


class CostPerOutcome(BaseModel):
    """What the spend bought. `None` where nothing was produced — an infinity
    printed as a number, or rounded to zero, would both read as "free"."""

    verified_companies: int
    didox_documents: int
    published_news: int
    uzs_per_verified_company: float | None
    uzs_per_document: float | None
    tokens_per_news_article: float | None


class AiAnalytics(BaseModel):
    window_days: int
    total_calls: int
    total_tokens_in: int
    total_tokens_out: int
    est_cost_usd: float
    by_purpose: list[AiPurposeStat]
    by_model: list[AiModelStat]
    daily: list[AiDayTokens]
    #: Echoed so a reader can see what the cost was computed from rather than
    #: trusting it — the token counts beside them are exact, these are estimates.
    assumed_rates_usd_per_mtok: dict[str, dict[str, float]]
    degradation: AiDegradation
    cost_per_outcome: CostPerOutcome
    has_data: bool
