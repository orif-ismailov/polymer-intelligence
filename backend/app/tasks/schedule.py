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

from celery.schedules import crontab

BEAT_SCHEDULE: dict[str, dict[str, object]] = {
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
    # ── CBU FX rates: daily at 07:00 Tashkent ────────────────────────────────
    "fetch_cbu_rates": {
        "task": "fetch_cbu_rates",
        "schedule": crontab(minute=0, hour=7),
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
}
