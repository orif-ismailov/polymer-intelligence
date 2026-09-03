"""
The arithmetic behind `/admin/analytics`, and the coverage guard.

Nothing here needs a database. What it protects is the class of bug this page is
most exposed to: a number that is confidently wrong. Every failure mode below
produces a plausible figure rather than an error, so none of them would announce
itself — a month boundary an hour out, a projection that divides by the wrong
day, quota counted for calls that never left the process, an AI feature quietly
missing from the totals.

The SQL these figures come out of is exercised in `test_analytics_db.py` against
a real Postgres; `percentile_cont` and `FILTER` have no SQLite equivalent worth
pretending about.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from app.services import analytics_service, llm_clients

TASHKENT = datetime.timezone(datetime.timedelta(hours=5))


def _at(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(iso)


class TestTheMonthIsTashkents:
    """The package resets on the operator's calendar, not on UTC's.

    Five hours of every month sit on the wrong side of a UTC boundary. Counted in
    UTC, the first five hours of a Tashkent month are attributed to the previous
    one — so the new month reads as barely started while the old one keeps
    growing after it ended, and both numbers look entirely reasonable.
    """

    def test_the_month_starts_at_tashkent_midnight(self) -> None:
        start, end, days, elapsed = analytics_service._month_bounds(
            _at("2026-09-15T10:00:00+00:00")
        )

        # 1 September 00:00 in Tashkent is 31 August 19:00 UTC.
        assert start == _at("2026-08-31T19:00:00+00:00")
        assert end == _at("2026-09-30T19:00:00+00:00")
        assert days == 30

    def test_the_last_evening_of_a_utc_month_is_already_the_next_one(self) -> None:
        """20:00 UTC on 31 August is 01:00 on 1 September in Tashkent."""
        start, _end, _days, elapsed = analytics_service._month_bounds(
            _at("2026-08-31T20:00:00+00:00")
        )

        assert start == _at("2026-08-31T19:00:00+00:00")  # September's start
        assert elapsed == 1  # first day of the new month, not the 31st

    def test_the_same_evening_an_hour_earlier_is_still_the_old_month(self) -> None:
        start, _end, _days, elapsed = analytics_service._month_bounds(
            _at("2026-08-31T18:00:00+00:00")
        )

        assert start == _at("2026-07-31T19:00:00+00:00")  # August's start
        assert elapsed == 31

    @pytest.mark.parametrize(
        ("moment", "days"),
        [
            ("2026-02-10T06:00:00+00:00", 28),  # February
            ("2028-02-10T06:00:00+00:00", 29),  # leap February
            ("2026-04-10T06:00:00+00:00", 30),
            ("2026-12-10T06:00:00+00:00", 31),
        ],
    )
    def test_month_length_is_the_real_one(self, moment: str, days: int) -> None:
        """The projection multiplies by this. A fixed 30 would understate a
        31-day month by a full day of traffic."""
        assert analytics_service._month_bounds(_at(moment))[2] == days

    def test_the_first_hour_of_a_month_divides_by_one_not_zero(self) -> None:
        """`days_elapsed` counts today, so a projection on day one is imprecise —
        which is honest — rather than a ZeroDivisionError, which is a 500 on the
        page an operator opens to find out what is going on."""
        _s, _e, _d, elapsed = analytics_service._month_bounds(_at("2026-09-01T00:30:00+05:00"))
        assert elapsed == 1


class TestEveryAiFeatureIsCounted:
    """A sixth LLM caller must not be able to appear without appearing here.

    Spend that is not counted is worse than spend that is not shown: the page
    reports a total, and a total missing a feature is a number an operator will
    plan against. `llm_clients._CLIENTS` is the list of modules that hold an LLM
    client, so it is the closest thing to a registry of AI features that exists.
    """

    #: The module → purpose mapping the union in `analytics_service` implements.
    #: `reports` appears twice over because both its clients live in one module.
    _EXPECTED = {
        "parsing.extractor": "signal_extraction",
        "parsing.news_extractor": "news_classification",
        "app.domains.news.reports": "report",
        "app.domains.requests.analysis": "request_analysis",
        "app.domains.compliance.substance_ai": "substance_hint",
    }

    def test_every_client_module_has_a_purpose(self) -> None:
        modules = {path for path, _wrapped in llm_clients._CLIENTS}
        assert modules == set(self._EXPECTED), (
            "a module holding an LLM client is not mapped to an analytics purpose — "
            "its tokens would be spent and never counted"
        )

    def test_every_purpose_appears_in_the_union(self) -> None:
        sql = analytics_service._AI_SOURCES
        for purpose in self._EXPECTED.values():
            assert f"'{purpose}'" in sql, f"{purpose} is mapped but not selected"

    def test_the_union_selects_nothing_else(self) -> None:
        """A purpose in the SQL that no module produces would be a column of
        zeros nobody can explain."""
        selected = set(re.findall(r"SELECT '(\w+)'", analytics_service._AI_SOURCES))
        assert selected == set(self._EXPECTED.values())


class TestTheDidoxRailIsMeasuredHonestly:
    def test_breaker_open_is_the_marker_the_client_actually_writes(self) -> None:
        """This constant is a contract with a string literal in another file. If
        the client renames it, quota consumption silently gains every call the
        breaker refused — inflating the bill exactly when the rail is broken."""
        client = (
            Path(__file__).resolve().parents[1] / "app" / "integrations" / "didox" / "client.py"
        ).read_text(encoding="utf-8")

        assert f'error="{analytics_service.NOT_SENT}"' in client

    def test_the_not_sent_rows_are_excluded_from_consumption(self) -> None:
        """Asserted on the SQL because the behaviour IS the WHERE clause: every
        consumption query has to carry the exclusion, and one that forgot would
        return a larger, entirely plausible number."""
        import inspect  # noqa: PLC0415

        source = inspect.getsource(analytics_service.didox_usage)
        # The per-operation, per-day and totals queries each need it.
        assert source.count("IS DISTINCT FROM :not_sent") >= 3


class TestCostRatesCoverWhatIsOffered:
    def test_every_offered_model_has_its_own_rate(self) -> None:
        """`rate_for` falls back to Sonnet's price. With two entries in the table
        that fallback covered almost every model an operator could pick — Haiku
        overstated fivefold, Opus understated — and the page would have printed
        it as a cost."""
        from app.services import settings_service  # noqa: PLC0415

        offered = set(settings_service.EXTRACT_MODELS) | set(settings_service.REPORT_MODELS)
        missing = sorted(offered - set(llm_clients.RATE_USD_PER_MTOK))
        assert not missing, f"no rate for {missing}; they would be costed as Sonnet"

    def test_a_longer_prefix_wins(self) -> None:
        """`gpt-5` is a prefix of `gpt-5-mini`; a first-match scan would price an
        unlisted `gpt-5-nano` at the flagship rate by dict ordering alone."""
        assert (
            llm_clients.rate_for("gpt-5-mini-2030") == llm_clients.RATE_USD_PER_MTOK["gpt-5-mini"]
        )
