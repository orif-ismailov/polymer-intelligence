"""
Centralized timezone helpers — DEC-tz-handling.

All timestamps in the database are stored as timestamptz/UTC.
Display is always in the configured TZ_DISPLAY zone (default Asia/Tashkent).

This module is the SINGLE place where timezone conversion happens.
Do NOT scatter tz conversions across the codebase — always import from here.

Rationale (dev-spec §10 risk 3): UZS trading is in Tashkent, SunSirs in Beijing,
futures in UTC+8 — storing only UTC and converting at display time is the only
safe approach.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

# Canonical display timezone — overridable via TZ_DISPLAY env var.
# We do NOT import settings at module load time to avoid circular imports;
# the tz parameter on to_display_tz() accepts a string to allow caller-supplied overrides.
_DEFAULT_TZ = "Asia/Tashkent"


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Use this everywhere instead of datetime.utcnow() (which is naïve and
    therefore ambiguous when stored alongside tz-aware values).
    """
    return datetime.now(tz=UTC)


def to_display_tz(dt: datetime, tz: str | tzinfo | None = None) -> datetime:
    """Convert an aware UTC datetime to the display timezone.

    Args:
        dt:  A timezone-aware datetime (should be UTC for correctness).
             If naïve, it is assumed to be UTC (with a deprecation warning).
        tz:  Optional override — either a IANA timezone name string (e.g.
             "Asia/Tashkent") or a tzinfo object.  Defaults to
             TZ_DISPLAY env var (Asia/Tashkent if not set).

    Returns:
        A timezone-aware datetime in the target display timezone.

    Raises:
        ValueError: if dt is naïve (no tzinfo).
    """
    if dt.tzinfo is None:
        raise ValueError(
            "to_display_tz() requires a timezone-aware datetime; "
            "got a naïve datetime.  Use utcnow() to create UTC timestamps."
        )

    # Resolve target timezone
    target: tzinfo
    if tz is None:
        # Lazy import to avoid circular dependency at module import time
        try:
            from app.core.config import settings  # noqa: PLC0415

            tz_name = settings.TZ_DISPLAY
        except Exception:  # pragma: no cover — settings not loaded in tests
            tz_name = _DEFAULT_TZ
        target = ZoneInfo(tz_name)
    elif isinstance(tz, str):
        target = ZoneInfo(tz)
    else:
        target = tz

    return dt.astimezone(target)
