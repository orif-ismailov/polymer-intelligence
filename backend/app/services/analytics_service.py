"""
What the two external bills are actually being spent on.

Both rails were already journalling everything this reads; nothing here adds a
write. `integration_call_log` has recorded every Didox and E-IMZO call since R3
and had never been read by anything, and the LLM callers journal tokens into four
different tables. This module is the query layer over both.

Two things it is careful about, because both would produce a confident wrong
number rather than an obvious failure:

**The month is Tashkent's.** The Didox package resets on the operator's calendar,
not on UTC's. A call at 20:30 UTC on the 31st already belongs to next month for
the person reading the page, and counting it in the old one would understate the
new month for its first hours and overstate the old one forever.

**`breaker_open` never reached Didox.** The client logs that row BEFORE it makes
a request — it is the circuit breaker refusing to try — so those calls cost no
quota. Counting them would inflate the bill exactly when the rail is broken and
the operator is most likely to be looking at this page. They are reported
separately instead, because a burst of them is a real fault worth seeing.
"""

from __future__ import annotations

import calendar
import datetime
from typing import Literal, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import to_display_tz, utcnow
from app.services import llm_clients, settings_service

#: Rows the client wrote without sending anything. Excluded from consumption and
#: counted on their own. `_log_call(…, error="breaker_open")` in
#: `app/integrations/didox/client.py` is the only place that writes it.
NOT_SENT = "breaker_open"


def _month_bounds(now: datetime.datetime | None = None) -> tuple[datetime.datetime, datetime.datetime, int, int]:
    """`(start_utc, end_utc, days_in_month, days_elapsed)` for the Tashkent month.

    `days_elapsed` counts the current day as one, so the first hour of the 1st
    divides by 1 rather than by 0 — a projection on day one is wildly imprecise,
    which is honest, where a `ZeroDivisionError` is a 500.
    """
    local = to_display_tz(now or utcnow(), settings.TZ_DISPLAY)
    start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(local.year, local.month)[1]
    end_local = start_local + datetime.timedelta(days=days_in_month)
    return (
        start_local.astimezone(datetime.UTC),
        end_local.astimezone(datetime.UTC),
        days_in_month,
        local.day,
    )


# ── Didox ─────────────────────────────────────────────────────────────────────


def didox_usage(db: Session, *, now: datetime.datetime | None = None) -> dict[str, object]:
    """This month's Didox consumption against the contracted package."""
    start, end, days_in_month, days_elapsed = _month_bounds(now)
    quota = settings_service.get_int("didox_monthly_quota")
    cost_uzs = settings_service.get_int("didox_monthly_cost_uzs")

    totals = (
        db.execute(
            sa.text(
                """
                SELECT
                  count(*) FILTER (WHERE error IS DISTINCT FROM :not_sent) AS billable,
                  count(*) FILTER (WHERE error = :not_sent)                AS not_sent,
                  count(*) FILTER (WHERE ok AND error IS DISTINCT FROM :not_sent) AS ok,
                  count(*) FILTER (WHERE NOT ok AND error IS DISTINCT FROM :not_sent) AS failed
                FROM integration_call_log
                WHERE provider = 'didox' AND created_at >= :start AND created_at < :end
                """
            ),
            {"start": start, "end": end, "not_sent": NOT_SENT},
        )
        .mappings()
        .one()
    )

    billable = int(totals["billable"] or 0)
    # Projection: today's pace held for the rest of the month. Simple on purpose —
    # a smarter model would be harder to check against the invoice, which is the
    # only thing this number is ever compared to.
    projected = round(billable / days_elapsed * days_in_month) if days_elapsed else billable
    # Where usage "should" be by now if the package were spent evenly. The meter's
    # marker, and the only thing that makes a mid-month number interpretable.
    pace = round(quota / days_in_month * days_elapsed) if days_in_month else 0

    by_operation = [
        {
            "operation": str(r["operation"]),
            "calls": int(r["calls"]),
            "ok": int(r["ok"]),
            "failed": int(r["failed"]),
            # `round`, not `int`: a truncated percentile disagrees by a millisecond
            # with the obvious `percentile_cont … round()` cross-check in psql,
            # which is the first thing anyone doubting this page will run.
            "p95_latency_ms": round(r["p95"]) if r["p95"] is not None else None,
        }
        for r in db.execute(
            sa.text(
                """
                SELECT operation,
                       count(*)                        AS calls,
                       count(*) FILTER (WHERE ok)      AS ok,
                       count(*) FILTER (WHERE NOT ok)  AS failed,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95
                FROM integration_call_log
                WHERE provider = 'didox'
                  AND created_at >= :start AND created_at < :end
                  AND error IS DISTINCT FROM :not_sent
                GROUP BY operation
                ORDER BY calls DESC
                """
            ),
            {"start": start, "end": end, "not_sent": NOT_SENT},
        ).mappings()
    ]

    by_day = [
        {"day": r["day"].date().isoformat(), "calls": int(r["calls"])}
        for r in db.execute(
            sa.text(
                """
                SELECT date_trunc('day', created_at AT TIME ZONE :tz) AS day, count(*) AS calls
                FROM integration_call_log
                WHERE provider = 'didox'
                  AND created_at >= :start AND created_at < :end
                  AND error IS DISTINCT FROM :not_sent
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"start": start, "end": end, "not_sent": NOT_SENT, "tz": settings.TZ_DISPLAY},
        ).mappings()
    ]

    failures = [
        {"error": str(r["error"]), "calls": int(r["calls"])}
        for r in db.execute(
            sa.text(
                """
                SELECT coalesce(error, 'unknown') AS error, count(*) AS calls
                FROM integration_call_log
                WHERE provider = 'didox' AND NOT ok
                  AND created_at >= :start AND created_at < :end
                GROUP BY 1 ORDER BY calls DESC
                """
            ),
            {"start": start, "end": end},
        ).mappings()
    ]

    return {
        "month_start": start.isoformat(),
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "quota": quota,
        "cost_uzs": cost_uzs,
        # What one call costs, for the cost-per-outcome tiles. Zero quota would be
        # a misconfiguration, not a free package.
        "uzs_per_call": round(cost_uzs / quota, 4) if quota else 0.0,
        "calls": billable,
        "ok": int(totals["ok"] or 0),
        "failed": int(totals["failed"] or 0),
        "not_sent": int(totals["not_sent"] or 0),
        "projected": projected,
        "pace": pace,
        "over_projection": projected > quota if quota else False,
        "spent_uzs": round(billable * (cost_uzs / quota), 2) if quota else 0.0,
        "by_operation": by_operation,
        "by_day": by_day,
        "failures": failures,
        # Lets the UI tell "nothing has run yet" from "we used none of it", which
        # read identically as a zero and mean opposite things.
        "has_data": billable > 0 or int(totals["not_sent"] or 0) > 0,
    }


def provider_health(db: Session, *, days: int = 30) -> list[dict[str, object]]:
    """Success rate and p95 latency per provider over the window.

    Covers E-IMZO as well as Didox — it is the same table and one extra `GROUP BY`,
    and the sidecar's reliability is the other thing nobody could see.
    """
    return [
        {
            "provider": str(r["provider"]),
            "calls": int(r["calls"]),
            "ok": int(r["ok"]),
            "success_pct": round(float(r["ok"]) / float(r["calls"]) * 100, 1) if r["calls"] else 0.0,
            # `round`, not `int`: a truncated percentile disagrees by a millisecond
            # with the obvious `percentile_cont … round()` cross-check in psql,
            # which is the first thing anyone doubting this page will run.
            "p95_latency_ms": round(r["p95"]) if r["p95"] is not None else None,
        }
        for r in db.execute(
            sa.text(
                """
                SELECT provider,
                       count(*)                   AS calls,
                       count(*) FILTER (WHERE ok) AS ok,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95
                FROM integration_call_log
                WHERE created_at >= now() - make_interval(days => :days)
                  AND error IS DISTINCT FROM :not_sent
                GROUP BY provider ORDER BY calls DESC
                """
            ),
            {"days": days, "not_sent": NOT_SENT},
        ).mappings()
    ]


# ── AI ────────────────────────────────────────────────────────────────────────

#: Every LLM caller, and the table it journals into.
#:
#: Four sources rather than one because each already had a home before this page
#: existed and none of them was built for it: `parse_runs` is the replay journal,
#: `substance_suggestions` is the seller's audit trail, and the other two record
#: tokens beside the thing they produced. Unioning them beats a fifth table that
#: would have to be written from five places and forgotten from one.
#:
#: `tests/test_analytics.py` asserts every module in `llm_clients._CLIENTS` is
#: represented here, so a sixth AI feature cannot be added and silently left out
#: of the totals.
_AI_SOURCES = """
    SELECT 'signal_extraction' AS purpose, model, tokens_in, tokens_out, created_at
      FROM parse_runs
     WHERE parser LIKE 'llm_extract%' AND model IS NOT NULL
    UNION ALL
    SELECT 'news_classification', model, tokens_in, tokens_out, created_at
      FROM parse_runs
     WHERE parser LIKE 'news_extract%' AND model IS NOT NULL
    UNION ALL
    SELECT 'substance_hint', model, tokens_in, tokens_out, created_at
      FROM substance_suggestions
     WHERE model IS NOT NULL
    UNION ALL
    SELECT 'request_analysis',
           ai ->> 'model',
           (ai ->> 'tokens_in')::int,
           (ai ->> 'tokens_out')::int,
           coalesce((ai ->> 'analyzed_at')::timestamptz, created_at)
      FROM requests
     WHERE ai ? 'tokens_in'
    UNION ALL
    SELECT 'report', split_part(generated_by, ' ', 1), tokens_in, tokens_out, created_at
      FROM reports
     WHERE tokens_in IS NOT NULL
"""


def ai_usage(db: Session, *, days: int = 30) -> dict[str, object]:
    """Token spend over the window, by what it was spent on and by model."""
    # ONE query grouped by both columns, rolled up twice in Python. The obvious
    # shape — a helper interpolating the GROUP BY column — meant building SQL with
    # an f-string, which ruff flags as an injection vector and is right to: the
    # value is safe today only because of who calls it, and that is exactly the
    # property that stops being true later. The cross-product is at most a handful
    # of purposes times a handful of models, so this is also one round trip
    # instead of two.
    # S608 flags any f-string that builds SQL, and rightly — but the only thing
    # interpolated here is `_AI_SOURCES`, a module constant a few lines up with no
    # interpolation of its own. Nothing from a request reaches either query; the
    # window is a bound parameter.
    totals_sql = f"""
        SELECT purpose, model,
               count(*)                        AS calls,
               coalesce(sum(tokens_in), 0)     AS tokens_in,
               coalesce(sum(tokens_out), 0)    AS tokens_out
        FROM ({_AI_SOURCES}) AS u
        WHERE created_at >= now() - make_interval(days => :days)
        GROUP BY purpose, model
    """  # noqa: S608
    rows = db.execute(sa.text(totals_sql), {"days": days}).mappings().all()

    def _rollup(key: Literal["purpose", "model"]) -> list[dict[str, object]]:
        totals: dict[str, tuple[int, int, int]] = {}
        for r in rows:
            label = str(r[key] or "unknown")
            calls, t_in, t_out = totals.get(label, (0, 0, 0))
            totals[label] = (
                calls + int(r["calls"]),
                t_in + int(r["tokens_in"]),
                t_out + int(r["tokens_out"]),
            )
        return [
            {
                key: label,
                "calls": calls,
                "tokens_in": t_in,
                "tokens_out": t_out,
                # Costed per MODEL only. A purpose can span several models, so a
                # cost against it would be a guess dressed as a figure; the
                # by-model table is the exact one.
                "est_cost_usd": llm_clients.est_cost(t_in, t_out, label)
                if key == "model"
                else None,
            }
            for label, (calls, t_in, t_out) in sorted(
                totals.items(), key=lambda kv: kv[1][1] + kv[1][2], reverse=True
            )
        ]

    by_purpose = _rollup("purpose")
    by_model = _rollup("model")

    daily_sql = f"""
        SELECT date_trunc('day', created_at AT TIME ZONE :tz) AS day,
               purpose,
               coalesce(sum(tokens_in), 0) + coalesce(sum(tokens_out), 0) AS tokens
        FROM ({_AI_SOURCES}) AS u
        WHERE created_at >= now() - make_interval(days => :days)
        GROUP BY 1, 2 ORDER BY 1
    """  # noqa: S608
    daily = [
        {
            "day": r["day"].date().isoformat(),
            "purpose": str(r["purpose"]),
            "tokens": int(r["tokens"]),
        }
        for r in db.execute(
            sa.text(daily_sql), {"days": days, "tz": settings.TZ_DISPLAY}
        ).mappings()
    ]

    # Narrowed here rather than read back out of the dicts: `dict[str, object]`
    # is what keeps `Any` out of the kernel, and `object` does not add.
    total_in = sum(cast(int, r["tokens_in"]) for r in by_purpose)
    total_out = sum(cast(int, r["tokens_out"]) for r in by_purpose)
    return {
        "window_days": days,
        "total_calls": sum(cast(int, r["calls"]) for r in by_purpose),
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "est_cost_usd": round(sum(cast(float, r["est_cost_usd"] or 0.0) for r in by_model), 4),
        "by_purpose": by_purpose,
        "by_model": by_model,
        "daily": daily,
        "assumed_rates_usd_per_mtok": llm_clients.RATE_USD_PER_MTOK,
        "has_data": bool(by_purpose),
    }


def ai_degradation(db: Session, *, days: int = 30) -> dict[str, object]:
    """Where the AI quietly did not work.

    Every LLM feature here degrades rather than errors — a failed extraction
    becomes a rule-based one, an exhausted budget defers the item, a failed digest
    falls back to a deterministic summary. Each is correct behaviour and each is
    silent, so without this panel a month of the AI being switched off by a bad
    key looks exactly like a month of the AI working.
    """
    row = (
        db.execute(
            sa.text(
                """
                SELECT
                  (SELECT count(*) FROM parse_runs
                    WHERE status = 'error' AND parser LIKE '%extract%'
                      AND created_at >= now() - make_interval(days => :days)) AS errors,
                  (SELECT count(*) FROM parse_runs
                    WHERE parser = 'rule_based_fallback'
                      AND created_at >= now() - make_interval(days => :days)) AS fallbacks,
                  (SELECT count(*) FROM raw_items
                    WHERE parse_status = 'budget_deferred')                   AS deferred,
                  (SELECT count(*) FROM reports
                    WHERE generated_by = 'rule_based'
                      AND created_at >= now() - make_interval(days => :days)) AS rule_based_reports,
                  (SELECT left(error, 300) FROM parse_runs
                    WHERE status = 'error' AND parser LIKE '%extract%'
                      AND created_at >= now() - make_interval(days => :days)
                    ORDER BY created_at DESC LIMIT 1)                         AS last_error
                """
            ),
            {"days": days},
        )
        .mappings()
        .one()
    )
    return {
        "errors": int(row["errors"] or 0),
        "fallbacks": int(row["fallbacks"] or 0),
        "deferred": int(row["deferred"] or 0),
        "rule_based_reports": int(row["rule_based_reports"] or 0),
        "last_error": row["last_error"],
    }


def cost_per_outcome(
    db: Session,
    *,
    days: int = 30,
    didox_spent_uzs: float,
    by_purpose: list[dict[str, object]],
) -> dict[str, object]:
    """What the two bills bought — the question "how much did we use" cannot answer.

    Each figure is `spend ÷ things produced` over the same window, and each is
    `None` when nothing was produced: dividing by zero would print an infinity,
    and rounding it to zero would read as "free".

    The spend figures are passed IN rather than recomputed. The caller has already
    run both aggregations to build the page; doing them again here would run the
    five-table union twice per request for numbers that must agree with the ones
    already on screen.
    """
    news_tokens = sum(
        cast(int, r["tokens_in"]) + cast(int, r["tokens_out"])
        for r in by_purpose
        if r.get("purpose") == "news_classification"
    )
    counts = (
        db.execute(
            sa.text(
                """
                SELECT
                  -- `decided_at`, not `created_at`: a case opened in June and
                  -- approved today was paid for by today's lookups, and this
                  -- table has no `updated_at` to fall back on.
                  (SELECT count(*) FROM verification_cases
                    WHERE status = 'approved'
                      AND decided_at >= now() - make_interval(days => :days))  AS verified,
                  (SELECT count(*) FROM didox_documents
                    WHERE created_at >= now() - make_interval(days => :days))  AS documents,
                  (SELECT count(*) FROM signals
                    WHERE kind = 'news'
                      AND event_at >= now() - make_interval(days => :days))    AS news
                """
            ),
            {"days": days},
        )
        .mappings()
        .one()
    )

    def _per(total: float, n: int) -> float | None:
        return round(total / n, 2) if n else None

    return {
        "verified_companies": int(counts["verified"] or 0),
        "didox_documents": int(counts["documents"] or 0),
        "published_news": int(counts["news"] or 0),
        "uzs_per_verified_company": _per(didox_spent_uzs, int(counts["verified"] or 0)),
        "uzs_per_document": _per(didox_spent_uzs, int(counts["documents"] or 0)),
        "tokens_per_news_article": _per(news_tokens, int(counts["news"] or 0)),
    }
