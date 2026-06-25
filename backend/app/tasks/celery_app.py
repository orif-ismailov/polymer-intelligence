"""
Celery application factory for Polymer Intelligence.

This module provides the `celery_app` instance that the worker and beat
containers reference via `celery -A app.tasks.celery_app worker/beat`.

Design notes:
- No hard Redis connection at import time — `broker_url` and `result_backend`
  are set as config strings; the actual TCP connection is deferred until a
  task is dispatched or the worker starts. This keeps the module import-safe
  under pytest without a live broker.
- json-only serialization (T-02-01): task_serializer="json",
  result_serializer="json", accept_content=["json"] — refuses pickle so a
  hostile broker message cannot execute arbitrary objects on deserialization.
- task_acks_late=True + worker_prefetch_multiplier=1 (T-02-02 / REQ-nfr-reliability):
  a crashed worker re-queues rather than silently dropping the in-flight fetch.
- Four queues exactly match the existing compose `-Q ingest,parse,notify,default`
  flag in deploy/docker-compose.dev.yml.
- beat_schedule is imported from app.tasks.schedule (Task 2) and attached to
  celery_app.conf so changing the schedule does not require editing this file.
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings

# ── Task modules to import at worker/beat startup ─────────────────────────────
# Every module that defines an @celery_app.task MUST be listed here. These are
# imported lazily when the app finalizes (worker boot / first dispatch), so there
# is no circular import with the task modules that import `celery_app` from here.
#
# Why not autodiscover_tasks(["app.tasks"])? With a single package argument Celery
# looks for the module `app.tasks.tasks` (its default related_name="tasks"), which
# does not exist in this project — so it imports NOTHING, the worker registers zero
# tasks, and every dispatched task is discarded as "Received unregistered task".
# An explicit include list is the deterministic fix.
_TASK_MODULES = [
    "app.tasks.ingest",
    "app.tasks.ingest_cbu",
    "app.tasks.parse",
    "app.tasks.parse_telegram",
    "app.tasks.notify",
    "app.tasks.userbot_health",
    "app.tasks.nightly_catchup",
    "app.tasks.rescore",
]

# ── Celery application instance ───────────────────────────────────────────────
celery_app = Celery("polymer_intelligence", include=_TASK_MODULES)

celery_app.conf.update(
    # ── Broker / result backend ───────────────────────────────────────────────
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    # Bound Redis connect/op time so a *producer* (e.g. an HTTP handler enqueuing a
    # notify task) fails fast instead of hanging on reconnect when Redis is down.
    # Workers still reconnect at startup via broker_connection_retry_on_startup;
    # this only caps each attempt. result_backend retry is capped because nothing in
    # this app blocks on task results (notifications are fire-and-forget).
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    result_backend_transport_options={
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
        "retry_policy": {"max_retries": 1},
    },
    redis_socket_connect_timeout=3,
    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone=settings.TZ_DISPLAY,  # "Asia/Tashkent" by default
    enable_utc=True,
    # ── Serialization (T-02-01: refuse pickle) ────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Reliability (T-02-02 / REQ-nfr-reliability) ───────────────────────────
    # Ack task only after it completes — a crashed worker re-queues rather than
    # silently dropping the in-flight message.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # ── Visibility ────────────────────────────────────────────────────────────
    task_track_started=True,
    # ── Startup ───────────────────────────────────────────────────────────────
    broker_connection_retry_on_startup=True,
    # ── Queue topology ────────────────────────────────────────────────────────
    # Four named queues exactly matching the compose `-Q ingest,parse,notify,default`
    # flag. Each queue uses the default direct exchange (kombu.Queue default).
    task_queues=[
        Queue("ingest"),
        Queue("parse"),
        Queue("notify"),
        Queue("default"),
    ],
    task_default_queue="default",
    # ── Routing ───────────────────────────────────────────────────────────────
    # Route ingest tasks to the "ingest" queue, parse tasks to "parse",
    # notify tasks to "notify". All other tasks fall through to "default".
    task_routes={
        "app.tasks.ingest.*": {"queue": "ingest"},
        "uzex_fetch_offers": {"queue": "ingest"},
        "uzex_fetch_contracts": {"queue": "ingest"},
        "uzex_fetch_deals": {"queue": "ingest"},
        "fetch_cbu_rates": {"queue": "ingest"},
        "check_source_health": {"queue": "ingest"},
        "check_userbot_health": {"queue": "ingest"},
        "app.tasks.parse.*": {"queue": "parse"},
        "parse_raw_item": {"queue": "parse"},
        "parse_telegram_item": {"queue": "parse"},
        "nightly_llm_catchup": {"queue": "parse"},
        "app.tasks.notify.*": {"queue": "notify"},
    },
)

# ── Task registration ─────────────────────────────────────────────────────────
# Tasks are registered via the explicit `include=_TASK_MODULES` list on the Celery
# constructor above (autodiscover_tasks(["app.tasks"]) is a no-op here — see the
# _TASK_MODULES comment). Add new task modules to that list.

# ── Beat schedule ─────────────────────────────────────────────────────────────
# Imported lazily to avoid a circular import: schedule.py imports crontab from
# celery.schedules but does NOT import celery_app itself.
from app.tasks.schedule import BEAT_SCHEDULE  # noqa: E402

celery_app.conf.beat_schedule = BEAT_SCHEDULE
