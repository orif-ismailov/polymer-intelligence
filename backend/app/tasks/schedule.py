"""
Celery beat schedule for Polymer Intelligence.

All schedules run in the Asia/Tashkent timezone (configured on celery_app.conf).

Crontab reference (SPEC §2 beat block):
  uzex_fetch_offers    — */15 9-18 * * 1-5   (every 15 min, business hours, weekdays)
  uzex_fetch_contracts — 0 * * * *            (hourly)
  uzex_fetch_deals     — 0 * * * *            (hourly)
  fetch_cbu_rates      — 0 7 * * *            (daily at 07:00 Tashkent)
  check_source_health  — */5 * * * *          (every 5 minutes)

Task names are STABLE CONTRACT STRINGS. The actual @celery_app.task(name=...) bodies
are implemented in later plans:
  - 02-04: uzex_fetch_offers, uzex_fetch_contracts, uzex_fetch_deals
  - 02-05: fetch_cbu_rates
  - 02-06: check_source_health

Until those plans land, thin placeholder tasks registered in this package ensure
the worker boots without "Task not registered" errors.
"""

from __future__ import annotations

from datetime import timedelta

from celery.schedules import crontab

BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    # ── Transactional-outbox dispatcher: every 15 s ──────────────────────────
    # Polls unpublished domain_events (FOR UPDATE SKIP LOCKED), fans out to
    # idempotent consumers, stamps published_at. Concurrency-safe: several
    # instances grab disjoint batches (R1 W2 — company verification outbox).
    "app.tasks.events.dispatch_domain_events": {
        "task": "app.tasks.events.dispatch_domain_events",
        "schedule": timedelta(seconds=15),
    },
    # ── UZEX offers: every 15 min, 09:00-18:00, Mon-Fri ─────────────────────
    "uzex_fetch_offers": {
        "task": "uzex_fetch_offers",
        "schedule": crontab(minute="*/15", hour="9-18", day_of_week="mon-fri"),
    },
    # ── UZEX contracts: every hour ────────────────────────────────────────────
    "uzex_fetch_contracts": {
        "task": "uzex_fetch_contracts",
        "schedule": crontab(minute=0),
    },
    # ── UZEX concluded deals: every hour ─────────────────────────────────────
    "uzex_fetch_deals": {
        "task": "uzex_fetch_deals",
        "schedule": crontab(minute=0),
    },
    # ── Xarid procurement tenders: every 30 min ──────────────────────────────
    # Buy-side demand from the public e-procurement portal (xarid.uzex.uz JSON API).
    # Only enabled sources run; the seeded source ships disabled until Tested.
    "xarid_fetch_tenders": {
        "task": "xarid_fetch_tenders",
        "schedule": crontab(minute="*/30"),
    },
    # ── CBU FX rates: daily at 07:00 Tashkent ────────────────────────────────
    "fetch_cbu_rates": {
        "task": "fetch_cbu_rates",
        "schedule": crontab(minute=0, hour=7),
    },
    # ── HTML table extraction: hourly at minute 15 ───────────────────────────
    # Fetches enabled html_table sources; structured rows route to the rule-based
    # parser (parse_raw_item) — product matching against the synonym dictionary,
    # no LLM cost. Offset from the minute-0 UZEX/CBU tasks to spread worker load.
    "html_table_fetch": {
        "task": "html_table_fetch",
        "schedule": crontab(minute=15),
    },
    # ── LLM page extraction: hourly at minute 30 ─────────────────────────────
    # Fetches enabled llm_page sources; each new page version is enqueued for
    # LLM extraction (parse_telegram_item), gated by the daily token budget.
    # Offset from the UZEX/CBU minute-0 tasks to spread worker load.
    "llm_page_fetch": {
        "task": "llm_page_fetch",
        "schedule": crontab(minute=30),
    },
    # ── News RSS refresh dispatcher: every minute ────────────────────────────
    # Enqueues rss_fetch only when the operator-configurable news_refresh_interval_minutes
    # (app_settings, default 60) has elapsed since the freshest enabled-RSS last_fetch_at.
    # Replaces the old fixed hourly rss_fetch entry so the scan cadence is runtime-tunable
    # from the dashboard admin panel (Phase 8f-2).
    "news_fetch_dispatch": {
        "task": "news_fetch_dispatch",
        "schedule": crontab(minute="*"),
    },
    # ── Source health check: every 5 minutes ─────────────────────────────────
    "check_source_health": {
        "task": "check_source_health",
        "schedule": crontab(minute="*/5"),
    },
    # ── Userbot heartbeat health check: every 5 minutes ──────────────────────
    # Reads the Redis heartbeat written by the userbot process (userbot:heartbeat).
    # Raises a deduped source_failure alert when the userbot has been silent
    # for more than USERBOT_SILENCE_SECONDS (300 s = 5 min) — ROADMAP SC#1.
    "check_userbot_health": {
        "task": "check_userbot_health",
        "schedule": crontab(minute="*/5"),
    },
    # ── Nightly LLM catch-up: daily at 02:00 UTC ─────────────────────────────
    # Reprocesses Telegram raw_items deferred during budget exhaustion
    # (parse_status='budget_deferred'). Runs after the UTC midnight budget reset.
    # Bounded batch (200 items max) to stay within the freshly-reset daily budget.
    # ROADMAP SC#4: budget→pending+rule-based fallback+nightly catch-up+admin alert.
    "nightly_llm_catchup": {
        "task": "nightly_llm_catchup",
        "schedule": crontab(minute=0, hour=2),
    },
    # ── Morning market report: 08:00 Tashkent ────────────────────────────────
    # Builds the morning brief as a draft; staff approve + publish on the
    # dashboard (human-in-the-loop — no auto-publish). Phase 3 news engine.
    "generate_daily_report": {
        "task": "generate_daily_report",
        "schedule": crontab(minute=0, hour=8),
    },
    # ── Evening market report: 18:00 Tashkent ────────────────────────────────
    # The second scheduled brief of the day (Phase 8c). Same 3-section structure,
    # tagged kind='evening'; also a draft for human-in-the-loop approval.
    "generate_evening_report": {
        "task": "generate_evening_report",
        "schedule": crontab(minute=0, hour=18),
    },
    # ── Breaking-news publisher: every 10 minutes ────────────────────────────
    # Pushes newly-detected high-importance news to the channel immediately, without
    # waiting for the next scheduled brief (Phase 8c). Deduped via signals.extra.
    "publish_breaking_news": {
        "task": "publish_breaking_news",
        "schedule": crontab(minute="*/10"),
    },
    # ── Portal notification retention: daily at 03:30 UTC ─────────────────────
    # Deletes read notifications older than 90 d and unread older than 365 d so the
    # portal_notifications table stays bounded (R2 W2 T2.3 / W6 T6.2).
    "prune_portal_notifications": {
        "task": "prune_portal_notifications",
        "schedule": crontab(minute=30, hour=3),
    },
    # ── Escrow provider inbox sweep: every 5 minutes (R6 / P7.b T2.2) ────────
    # The webhook commits the `provider_events` row BEFORE enqueuing its applier,
    # so a Redis blip costs latency rather than evidence. This is the other half
    # of that bargain: anything still unprocessed gets applied here. Idempotent.
    "sweep_provider_events": {
        "task": "sweep_provider_events",
        "schedule": crontab(minute="*/5"),
    },
    # ── Contract PDF integrity: daily at 03:00 UTC (R3 TB4.1) ─────────────────
    # Recomputes stored-PDF sha256 vs document_sha256 for active contracts and
    # alerts the admin channel on any mismatch (tamper detection).
    "verify_contract_integrity": {
        "task": "verify_contract_integrity",
        "schedule": crontab(minute=0, hour=3),
    },
    # ── Contract expiry: daily at 04:00 UTC (R3 TB4.2) ───────────────────────
    # Expires contracts inactive in pending_counterparty/pending_signatures beyond
    # contract_pending_ttl_days (default 30) + notifies both parties.
    "expire_stale_contracts": {
        "task": "expire_stale_contracts",
        "schedule": crontab(minute=0, hour=4),
    },
}
