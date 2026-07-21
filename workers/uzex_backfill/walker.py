"""The walk loop — fetch → parse → store, id by id.

Responsibilities:

* **Politeness** — one global rate limit (default 1 req/s), single-threaded.
* **Backoff** — 429/403 and sustained outages trigger an exponential 60s→1h
  backoff; the same id is retried (no data loss) rather than skipped. A heartbeat
  keeps the concurrent-run lock fresh *during* long sleeps so a second process
  never starts mid-outage.
* **Resumability** — a DB checkpoint (high-water mark) is written periodically
  and on shutdown; a resume starts at ``checkpoint + 1``.
* **Idempotency** — every row upserts on ``(source, external_id, content_hash)``
  with DO NOTHING, so a re-walk inserts zero duplicates.
* **raw_html policy** — gzip'd raw HTML is stored ONLY on anomalies (parse_empty,
  <5 parsed fields on a 200, or a never-before-seen label's first occurrence).
* **Graceful stop** — a SIGTERM flag finishes the in-flight id, commits, exits 0.
"""

from __future__ import annotations

import gzip
import time
from dataclasses import dataclass, field

import psycopg

from . import db
from .config import Config
from .fetcher import (
    OUTCOME_BLOCKED,
    OUTCOME_FAILED,
    OUTCOME_FETCHED,
    OUTCOME_HTTP_NOT_FOUND,
    Fetcher,
    FetchResult,
)
from .log import log
from .parser import (
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_PARSE_EMPTY,
    hash_fields,
    parse_detail,
    status_sentinel_hash,
)

STATUS_FETCH_FAILED = "fetch_failed"


@dataclass
class WalkStats:
    ok: int = 0
    not_found: int = 0
    parse_empty: int = 0
    fetch_failed: int = 0
    inserted: int = 0
    duplicate: int = 0
    processed: int = 0
    new_labels: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "ok": self.ok,
            "not_found": self.not_found,
            "parse_empty": self.parse_empty,
            "fetch_failed": self.fetch_failed,
            "inserted": self.inserted,
            "duplicate": self.duplicate,
            "new_labels": self.new_labels,
        }


@dataclass
class Walker:
    config: Config
    conn: psycopg.Connection
    fetcher: Fetcher
    stats: WalkStats = field(default_factory=WalkStats)

    def __post_init__(self) -> None:
        self._stop = False
        self.known_labels = db.load_known_labels(self.conn)
        self._highest_done = 0
        self._last_ckpt_id = 0
        self._last_ckpt_time = time.monotonic()
        self._last_request_at = 0.0
        self._last_heartbeat = time.monotonic()
        self._heartbeat_interval = max(5.0, min(self.config.stale_lock_seconds / 2.0, 120.0))

    # -- shutdown ----------------------------------------------------------
    def request_stop(self) -> None:
        self._stop = True

    # -- rate limiting -----------------------------------------------------
    def _throttle(self) -> None:
        interval = self.config.min_request_interval()
        if interval <= 0:
            return
        earliest = self._last_request_at + interval
        now = time.monotonic()
        if now < earliest:
            self._interruptible_sleep(earliest - now)
        self._last_request_at = time.monotonic()

    def _interruptible_sleep(self, seconds: float, *, heartbeat: bool = False) -> None:
        """Sleep in small chunks so SIGTERM is honoured promptly; optionally
        refresh the DB heartbeat so the concurrent-run lock stays alive."""
        deadline = time.monotonic() + seconds
        while not self._stop:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.5))
            if heartbeat and (time.monotonic() - self._last_heartbeat >= self._heartbeat_interval):
                self._heartbeat()

    # -- checkpoint / heartbeat -------------------------------------------
    def _heartbeat(self) -> None:
        db.write_checkpoint(self.conn, self.config.worker_name, self._highest_done)
        now = time.monotonic()
        self._last_heartbeat = now
        self._last_ckpt_time = now

    def _checkpoint(self, offer_id: int) -> None:
        db.write_checkpoint(self.conn, self.config.worker_name, offer_id)
        now = time.monotonic()
        self._last_ckpt_id = offer_id
        self._last_ckpt_time = now
        self._last_heartbeat = now

    def _checkpoint_if_due(self, offer_id: int) -> None:
        self._highest_done = offer_id
        due_by_count = offer_id - self._last_ckpt_id >= self.config.checkpoint_every
        due_by_time = (
            time.monotonic() - self._last_ckpt_time >= self.config.checkpoint_interval_seconds
        )
        if due_by_count or due_by_time:
            self._checkpoint(offer_id)

    def _next_backoff(self, current: float) -> float:
        if current <= 0:
            return self.config.backoff_start_seconds
        return min(current * 2.0, self.config.backoff_max_seconds)

    # -- fetch with backoff ------------------------------------------------
    def _fetch_resolved(self, offer_id: int) -> FetchResult | None:
        """Fetch one id, riding out blocks/outages with the long backoff.

        Returns a terminal :class:`FetchResult` — ``fetched`` / ``http_not_found``
        normally, or ``failed`` when we give up after ``max_hard_retries``. Returns
        ``None`` if a stop was requested before a terminal result (nothing to
        store for this id).
        """
        long_backoff = 0.0
        hard_cycles = 0
        while not self._stop:
            self._throttle()
            if self._stop:
                return None
            result = self.fetcher.fetch(offer_id)

            if result.outcome in (OUTCOME_FETCHED, OUTCOME_HTTP_NOT_FOUND):
                return result

            if result.outcome == OUTCOME_BLOCKED:
                long_backoff = self._next_backoff(long_backoff)
                log(
                    "backoff",
                    id=offer_id,
                    reason="blocked",
                    http_status=result.http_status,
                    sleep_seconds=long_backoff,
                )
                self._heartbeat()
                self._interruptible_sleep(long_backoff, heartbeat=True)
                continue  # wait a block out — never give up

            # OUTCOME_FAILED — network/5xx persisted through per-id retries
            hard_cycles += 1
            if hard_cycles > self.config.max_hard_retries:
                return result  # caller records fetch_failed and advances
            long_backoff = self._next_backoff(long_backoff)
            log(
                "backoff",
                id=offer_id,
                reason="failed",
                cycle=hard_cycles,
                http_status=result.http_status,
                error=result.error,
                sleep_seconds=long_backoff,
            )
            self._heartbeat()
            self._interruptible_sleep(long_backoff, heartbeat=True)

        return None

    # -- main contiguous walk ---------------------------------------------
    def run(self, start_id: int, end_id: int) -> WalkStats:
        self._highest_done = start_id - 1
        self._last_ckpt_id = start_id - 1
        log(
            "walk_start",
            worker=self.config.worker_name,
            start_id=start_id,
            end_id=end_id,
            rps=self.config.rate_limit_rps,
            environment=self.config.environment,
        )

        offer_id = start_id
        while offer_id <= end_id and not self._stop:
            t0 = time.monotonic()
            result = self._fetch_resolved(offer_id)
            if result is None:  # stopped before a terminal result
                break
            duration_ms = round((time.monotonic() - t0) * 1000, 1)

            status, field_count = self._store_result(offer_id, result)
            self.stats.processed += 1
            self._log_id(offer_id, status, duration_ms, field_count, result)
            self._checkpoint_if_due(offer_id)
            if self.stats.processed % 1000 == 0:
                self._summary(offer_id)
            offer_id += 1

        if self._highest_done >= start_id:
            self._checkpoint(self._highest_done)
        self._summary(self._highest_done, final=True)
        return self.stats

    # -- retry a discrete list (retry-failed) ------------------------------
    def retry_ids(self, ids: list[int]) -> WalkStats:
        self._highest_done = db.get_checkpoint(self.conn, self.config.worker_name) or 0
        log("retry_start", worker=self.config.worker_name, count=len(ids))
        for offer_id in ids:
            if self._stop:
                break
            t0 = time.monotonic()
            result = self._fetch_resolved(offer_id)
            if result is None:
                break
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            status, field_count = self._store_result(offer_id, result)
            self.stats.processed += 1
            self._log_id(offer_id, status, duration_ms, field_count, result)
        self._summary(self._highest_done, final=True)
        return self.stats

    # -- storage -----------------------------------------------------------
    def _store_result(self, offer_id: int, result: FetchResult) -> tuple[str, int]:
        if result.outcome == OUTCOME_HTTP_NOT_FOUND:
            return self._store_simple(offer_id, result, STATUS_NOT_FOUND)
        if result.outcome == OUTCOME_FAILED:
            return self._store_simple(offer_id, result, STATUS_FETCH_FAILED)
        return self._store_fetched(offer_id, result)

    def _store_fetched(self, offer_id: int, result: FetchResult) -> tuple[str, int]:
        parse = parse_detail(result.text or "")

        if parse.status != STATUS_OK:
            # not_found (empty template) keeps no raw; parse_empty keeps raw for forensics
            raw = None
            if parse.status == STATUS_PARSE_EMPTY:
                raw = gzip.compress((result.text or "").encode("utf-8"))
            inserted = db.upsert_offer(
                self.conn,
                source=self.config.worker_name,
                external_id=offer_id,
                http_status=result.http_status,
                final_url=result.final_url,
                status=parse.status,
                fields=None,
                raw_html=raw,
                content_hash=status_sentinel_hash(parse.status),
            )
            self._tally(parse.status, inserted)
            return parse.status, 0

        fields = parse.fields
        content_hash = hash_fields(fields)
        unique_labels = list(dict.fromkeys(parse.labels))
        new_labels = [lbl for lbl in unique_labels if lbl not in self.known_labels]
        field_count = parse.field_count

        # anomaly-only raw_html: thin page OR a never-seen-before label (first time)
        store_raw = field_count < 5 or bool(new_labels)
        raw = gzip.compress((result.text or "").encode("utf-8")) if store_raw else None

        inserted = db.upsert_offer(
            self.conn,
            source=self.config.worker_name,
            external_id=offer_id,
            http_status=result.http_status,
            final_url=result.final_url,
            status=STATUS_OK,
            fields=fields,
            raw_html=raw,
            content_hash=content_hash,
        )
        self._tally(STATUS_OK, inserted)

        if new_labels:
            db.insert_labels(self.conn, {lbl: offer_id for lbl in new_labels})
            self.known_labels.update(new_labels)
            self.stats.new_labels += len(new_labels)
        return STATUS_OK, field_count

    def _store_simple(self, offer_id: int, result: FetchResult, status: str) -> tuple[str, int]:
        inserted = db.upsert_offer(
            self.conn,
            source=self.config.worker_name,
            external_id=offer_id,
            http_status=result.http_status,
            final_url=result.final_url,
            status=status,
            fields=None,
            raw_html=None,
            content_hash=status_sentinel_hash(status),
        )
        self._tally(status, inserted)
        return status, 0

    def _tally(self, status: str, inserted: bool) -> None:
        setattr(self.stats, status, getattr(self.stats, status) + 1)
        if inserted:
            self.stats.inserted += 1
        else:
            self.stats.duplicate += 1

    # -- logging -----------------------------------------------------------
    def _log_id(
        self, offer_id: int, status: str, duration_ms: float, field_count: int, result: FetchResult
    ) -> None:
        log(
            "id",
            id=offer_id,
            status=status,
            http_status=result.http_status,
            duration_ms=duration_ms,
            fields=field_count,
        )

    def _summary(self, offer_id: int, *, final: bool = False) -> None:
        log(
            "summary_final" if final else "summary",
            worker=self.config.worker_name,
            checkpoint=self._highest_done,
            current_id=offer_id,
            **self.stats.as_dict(),
        )
