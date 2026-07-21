"""Structured JSON-lines logging to stdout.

One JSON object per line so the output is greppable and ingestible by any log
pipeline. Kept dependency-free on purpose (no structlog) — this worker ships its
own minimal requirements.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


def log(event: str, **fields: Any) -> None:
    """Emit a single structured log line to stdout.

    ``ts`` is wall-clock epoch seconds (UTC). Values that are not JSON
    serializable are coerced to ``str`` so logging never raises.
    """
    record: dict[str, Any] = {"ts": round(time.time(), 3), "event": event}
    record.update(fields)
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        line = json.dumps(
            {"ts": record["ts"], "event": event, "log_error": "unserializable"},
        )
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
