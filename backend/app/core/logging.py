"""
Structured JSON logging configuration — REQ-nfr-observability.

Uses structlog to emit JSON lines to stdout so that docker logs (and optionally
Loki) can ingest them without further parsing.

Each log line contains at minimum: timestamp (ISO-8601 UTC), log_level, logger,
and event.  Additional key=value pairs are merged in automatically.

Call configure_logging() once at application startup (from create_app()).
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog to render JSON to stdout.

    Args:
        log_level: Standard Python log level name (DEBUG, INFO, WARNING, etc.)
                   Defaults to INFO.  In development you may pass DEBUG.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Route stdlib logging through structlog so third-party libraries
    # (sqlalchemy, uvicorn, celery) also emit structured JSON.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Attach the JSON renderer to the stdlib formatter so all stdlib log records
    # are also rendered as JSON.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Remove the basicConfig handler and replace with the structured one.
    root_logger.handlers = [handler]
    root_logger.setLevel(level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("event", key="value")
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
