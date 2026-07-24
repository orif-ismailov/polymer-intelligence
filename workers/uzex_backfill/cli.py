"""Command-line interface: ``python -m uzex_backfill <subcommand>``.

Subcommands
-----------
* ``init-db``      — apply the standalone schema (idempotent).
* ``probe``        — characterize boundary/failure ids; writes nothing.
* ``run``          — the walk (defaults: from checkpoint, to configured max).
* ``retry-failed`` — re-fetch ids currently marked ``fetch_failed``.
* ``status``       — checkpoint, counts by status, rough ETA.
"""

from __future__ import annotations

import argparse
import signal
import sys

from . import db
from .config import Config, ConfigError, load_config
from .fetcher import Fetcher
from .log import log
from .probe import DEFAULT_PROBE_IDS, run_probe
from .walker import Walker


def _install_signal_handlers(walker: Walker) -> None:
    def handler(signum: int, _frame: object) -> None:
        log("signal", signal=signal.Signals(signum).name, action="graceful_stop")
        walker.request_stop()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _guard_concurrent_run(config: Config, conn: db.psycopg.Connection, force: bool) -> bool:
    """Return True if it is safe to start; False (with a logged reason) if another
    worker updated the checkpoint within ``stale_lock_seconds``."""
    age = db.seconds_since_checkpoint(conn, config.worker_name)
    if age is not None and age < config.stale_lock_seconds and not force:
        log(
            "concurrent_run_refused",
            worker=config.worker_name,
            seconds_since_checkpoint=round(age, 1),
            stale_lock_seconds=config.stale_lock_seconds,
            hint="another worker looks active; pass --force to override",
        )
        return False
    return True


# -- subcommands -----------------------------------------------------------
def cmd_init_db(config: Config, _args: argparse.Namespace) -> int:
    with db.connect(config.database_url) as conn:
        db.apply_schema(conn)
    log("init_db", status="applied", database="<dsn>")
    return 0


def cmd_probe(config: Config, args: argparse.Namespace) -> int:
    ids = _parse_ids(args.ids) if args.ids else list(DEFAULT_PROBE_IDS)
    with Fetcher(config) as fetcher:
        run_probe(config, fetcher, ids)
    return 0


def cmd_run(config: Config, args: argparse.Namespace) -> int:
    with db.connect(config.database_url) as conn:
        db.apply_schema(conn)

        if config.is_dev and (args.from_id is None or args.to_id is None):
            log(
                "dev_rail",
                error="in dev, `run` requires explicit --from and --to",
                effective_max_id=config.effective_max_id,
            )
            return 2

        if not _guard_concurrent_run(config, conn, args.force):
            return 3

        checkpoint = db.get_checkpoint(conn, config.worker_name)
        start = (
            args.from_id
            if args.from_id is not None
            else (checkpoint + 1 if checkpoint is not None else config.min_id)
        )
        end = args.to_id if args.to_id is not None else config.effective_max_id
        end = min(end, config.effective_max_id)  # hard cap (enforces dev ceiling)
        start = max(start, config.min_id)

        if start > end:
            log("nothing_to_do", start_id=start, end_id=end, checkpoint=checkpoint)
            return 0

        with Fetcher(config) as fetcher:
            fetcher.pin_language()
            walker = Walker(config=config, conn=conn, fetcher=fetcher)
            _install_signal_handlers(walker)
            stats = walker.run(start, end)
        log("run_done", **stats.as_dict())
    return 0


def cmd_retry_failed(config: Config, args: argparse.Namespace) -> int:
    with db.connect(config.database_url) as conn:
        db.apply_schema(conn)
        if not _guard_concurrent_run(config, conn, args.force):
            return 3
        ids = db.failed_external_ids(conn, config.worker_name, limit=args.limit)
        if not ids:
            log("retry_failed", status="nothing_to_retry")
            return 0
        with Fetcher(config) as fetcher:
            fetcher.pin_language()
            walker = Walker(config=config, conn=conn, fetcher=fetcher)
            _install_signal_handlers(walker)
            stats = walker.retry_ids(ids)
        log("retry_done", **stats.as_dict())
    return 0


def cmd_status(config: Config, _args: argparse.Namespace) -> int:
    with db.connect(config.database_url) as conn:
        checkpoint = db.get_checkpoint(conn, config.worker_name)
        age = db.seconds_since_checkpoint(conn, config.worker_name)
        counts = db.status_counts(conn, config.worker_name)
        lo, hi = db.offer_id_bounds(conn, config.worker_name)
        labels = db.label_count(conn)

    remaining = None
    eta_seconds = None
    if checkpoint is not None:
        remaining = max(0, config.effective_max_id - checkpoint)
        if config.rate_limit_rps > 0:
            eta_seconds = round(remaining / config.rate_limit_rps)

    log(
        "status",
        worker=config.worker_name,
        environment=config.environment,
        checkpoint=checkpoint,
        seconds_since_checkpoint=round(age, 1) if age is not None else None,
        worker_active=(age is not None and age < config.stale_lock_seconds),
        effective_max_id=config.effective_max_id,
        remaining_ids=remaining,
        eta_seconds=eta_seconds,
        eta_human=_human_duration(eta_seconds) if eta_seconds is not None else None,
        counts=counts,
        stored_id_range=[lo, hi],
        discovered_labels=labels,
    )
    return 0


# -- helpers ---------------------------------------------------------------
def _parse_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.replace(",", " ").split()]


def _human_duration(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uzex_backfill",
        description="Standalone UZEX offer-detail archive backfill worker.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="apply the standalone schema (idempotent)")

    p_probe = sub.add_parser("probe", help="characterize boundary/failure ids; writes nothing")
    p_probe.add_argument("--ids", help="comma/space separated ids (default: a built-in spread)")

    p_run = sub.add_parser("run", help="walk the id range")
    p_run.add_argument("--from", dest="from_id", type=int, help="start id (default: checkpoint+1)")
    p_run.add_argument("--to", dest="to_id", type=int, help="end id (default: configured max)")
    p_run.add_argument(
        "--force", action="store_true", help="override the concurrent-run guard"
    )

    p_retry = sub.add_parser("retry-failed", help="re-fetch ids marked fetch_failed")
    p_retry.add_argument("--limit", type=int, help="max ids to retry this run")
    p_retry.add_argument("--force", action="store_true", help="override the concurrent-run guard")

    sub.add_parser("status", help="progress, counts by status, ETA")
    return parser


_DISPATCH = {
    "init-db": cmd_init_db,
    "probe": cmd_probe,
    "run": cmd_run,
    "retry-failed": cmd_retry_failed,
    "status": cmd_status,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        log("config_error", error=str(exc))
        return 2
    handler = _DISPATCH[args.command]
    try:
        return handler(config, args)
    except KeyboardInterrupt:
        log("interrupted")
        return 130
    except Exception as exc:  # never crash silently; surface and exit non-zero
        log("fatal", error=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
