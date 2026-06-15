"""
Unit tests for app.core.time — timezone helper.

DEC-tz-handling: UTC in DB, Asia/Tashkent display, market-local observed dates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.time import to_display_tz, utcnow


class TestUtcNow:
    def test_returns_aware_datetime(self) -> None:
        """utcnow() must return a timezone-aware datetime."""
        now = utcnow()
        assert now.tzinfo is not None

    def test_tzinfo_is_utc(self) -> None:
        """utcnow() tzinfo must represent UTC (offset == 0)."""
        now = utcnow()
        assert now.utcoffset() == timedelta(0)

    def test_is_recent(self) -> None:
        """utcnow() should be within a few seconds of actual UTC."""
        now = utcnow()
        actual_now = datetime.now(tz=UTC)
        delta = abs((actual_now - now).total_seconds())
        assert delta < 5


class TestToDisplayTz:
    # Asia/Tashkent is UTC+5 (no DST)
    _TZ = "Asia/Tashkent"
    _OFFSET = timedelta(hours=5)

    def test_converts_utc_to_tashkent(self) -> None:
        """A known UTC instant must produce the correct Asia/Tashkent wall-clock time."""
        # 2024-01-15 00:00:00 UTC → 2024-01-15 05:00:00 +05:00 in Tashkent
        utc_dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        local_dt = to_display_tz(utc_dt, tz=self._TZ)

        assert local_dt.year == 2024
        assert local_dt.month == 1
        assert local_dt.day == 15
        assert local_dt.hour == 5
        assert local_dt.minute == 0
        assert local_dt.second == 0
        assert local_dt.utcoffset() == self._OFFSET

    def test_offset_is_plus_five(self) -> None:
        """Asia/Tashkent offset is always +05:00 (no DST)."""
        utc_dt = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)
        local_dt = to_display_tz(utc_dt, tz=self._TZ)
        assert local_dt.utcoffset() == self._OFFSET

    def test_result_is_aware(self) -> None:
        """Result must be timezone-aware."""
        utc_dt = datetime(2024, 3, 1, 8, 0, 0, tzinfo=UTC)
        local_dt = to_display_tz(utc_dt, tz=self._TZ)
        assert local_dt.tzinfo is not None

    def test_naïve_input_raises(self) -> None:
        """Passing a naïve datetime must raise ValueError."""
        naïve = datetime(2024, 1, 1, 0, 0, 0)
        with pytest.raises(ValueError, match="timezone-aware"):
            to_display_tz(naïve, tz=self._TZ)

    def test_accepts_tzinfo_object(self) -> None:
        """tz parameter accepts a ZoneInfo object as well as a string."""
        utc_dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        tz_obj = ZoneInfo(self._TZ)
        local_dt = to_display_tz(utc_dt, tz=tz_obj)
        assert local_dt.utcoffset() == self._OFFSET

    def test_midnight_utc_is_morning_tashkent(self) -> None:
        """Midnight UTC should be 05:00 AM in Tashkent."""
        utc_dt = datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC)
        local_dt = to_display_tz(utc_dt, tz=self._TZ)
        assert local_dt.hour == 5
        assert local_dt.date().isoformat() == "2024-06-01"

    def test_late_night_utc_crosses_midnight_tashkent(self) -> None:
        """23:00 UTC should become 04:00 next day in Tashkent."""
        utc_dt = datetime(2024, 6, 1, 23, 0, 0, tzinfo=UTC)
        local_dt = to_display_tz(utc_dt, tz=self._TZ)
        assert local_dt.hour == 4
        assert local_dt.day == 2  # crossed midnight to next day
