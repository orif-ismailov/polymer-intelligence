"""
The analytics queries against a real Postgres.

Separate from `test_analytics.py` because none of this can be faked: `FILTER
(WHERE …)`, `percentile_cont … WITHIN GROUP`, `AT TIME ZONE`, `ai ? 'tokens_in'`
and a five-arm `UNION ALL` are Postgres, and a stubbed session would only assert
that the strings I wrote are the strings I wrote.

The queries were written against the real schema and three of them were wrong in
ways only the database could report — a column named `updated_at` that does not
exist on `verification_cases`, and `reports.tokens_in` before its migration ran.
That is the whole argument for this file.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_analytics_db.py -q
"""

from __future__ import annotations

import datetime
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Analytics DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def migrated(engine: sa.Engine) -> sa.Engine:
    from app.core.config import settings  # noqa: PLC0415

    try:
        settings.DATABASE_URL = _DB_URL
    except Exception:  # noqa: BLE001 — frozen settings: bypass validation
        object.__setattr__(settings, "DATABASE_URL", _DB_URL)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    return engine


#: Every table these tests write to. Analytics is all aggregates, so a row left
#: behind by one test is a wrong total in the next — and, because the cleanup
#: also runs at setup, a wrong total in the next RUN. Cleaning only the call log
#: was enough to make two report assertions read 8000 tokens where 4000 were
#: inserted, which is exactly the failure this list prevents.
_TABLES = ("integration_call_log", "reports")


@pytest.fixture
def db(migrated: sa.Engine) -> Generator[Session, None, None]:
    """A clean slate per test, before and after."""
    from app.services import settings_service  # noqa: PLC0415

    def _truncate(session: Session) -> None:
        for table in _TABLES:
            session.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 — fixed tuple above
        session.commit()

    factory = sessionmaker(bind=migrated, expire_on_commit=False)
    with factory() as session:
        _truncate(session)
        try:
            yield session
        finally:
            session.rollback()
            _truncate(session)
            settings_service.clear_snapshot()


def _log(
    db: Session,
    *,
    provider: str = "didox",
    operation: str = "info_by_tin",
    ok: bool = True,
    latency: int | None = 100,
    error: str | None = None,
    at: datetime.datetime | None = None,
) -> None:
    db.execute(
        sa.text(
            """
            INSERT INTO integration_call_log
                (provider, operation, ok, status_code, latency_ms, error, created_at)
            VALUES (:p, :o, :ok, 200, :lat, :err, coalesce(:at, now()))
            """
        ),
        {"p": provider, "o": operation, "ok": ok, "lat": latency, "err": error, "at": at},
    )
    db.commit()


@_requires_real_db
class TestQuotaConsumption:
    def test_calls_this_month_are_counted(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        for _ in range(3):
            _log(db)

        assert analytics_service.didox_usage(db)["calls"] == 3

    def test_breaker_open_rows_never_touch_consumption(self, db: Session) -> None:
        """They are written BEFORE any request leaves the process. Counting them
        would inflate the bill exactly when the rail is broken — the moment an
        operator is most likely to be reading this page."""
        from app.services import analytics_service  # noqa: PLC0415

        _log(db)
        _log(db, ok=False, error=analytics_service.NOT_SENT, latency=None)
        _log(db, ok=False, error=analytics_service.NOT_SENT, latency=None)

        usage = analytics_service.didox_usage(db)

        assert usage["calls"] == 1
        assert usage["not_sent"] == 2
        # Reported, not hidden: a burst of them is a real fault.
        assert usage["has_data"] is True

    def test_a_failed_call_still_costs_quota(self, db: Session) -> None:
        """It reached Didox and came back 4xx. The package is charged per
        request, not per useful answer."""
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, ok=False, error="didox_4xx")

        usage = analytics_service.didox_usage(db)
        assert (usage["calls"], usage["failed"], usage["not_sent"]) == (1, 1, 0)

    def test_last_months_calls_are_not_counted(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=60))

        usage = analytics_service.didox_usage(db)
        assert usage["calls"] == 0
        assert usage["has_data"] is False

    def test_an_empty_month_reports_zero_rather_than_failing(self, db: Session) -> None:
        """A fresh deployment. `has_data` is what lets the page say "nothing has
        run yet" instead of drawing a confident 0 next to a million-call quota."""
        from app.services import analytics_service  # noqa: PLC0415

        usage = analytics_service.didox_usage(db)

        assert usage["calls"] == 0
        assert usage["has_data"] is False
        assert usage["by_operation"] == []
        assert usage["spent_uzs"] == 0.0

    def test_spend_follows_the_configured_package(self, db: Session) -> None:
        """The quota and price are settings, so the arithmetic has to read them
        rather than a constant — otherwise a renegotiated contract silently keeps
        billing at the old rate on screen."""
        from app.services import analytics_service  # noqa: PLC0415
        from tests.conftest import set_switch  # noqa: PLC0415

        for _ in range(4):
            _log(db)
        set_switch(didox_monthly_quota=1000, didox_monthly_cost_uzs=500)

        usage = analytics_service.didox_usage(db)

        assert usage["uzs_per_call"] == 0.5
        assert usage["spent_uzs"] == 2.0  # 4 calls × 0.5


@_requires_real_db
class TestPerOperationBreakdown:
    def test_operations_are_split_and_ranked(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        for _ in range(3):
            _log(db, operation="info_by_tin")
        _log(db, operation="auth_by_password")

        rows = analytics_service.didox_usage(db)["by_operation"]

        assert [r["operation"] for r in rows] == ["info_by_tin", "auth_by_password"]
        assert rows[0]["calls"] == 3

    def test_p95_with_a_single_row_is_that_row(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, latency=250)

        assert analytics_service.didox_usage(db)["by_operation"][0]["p95_latency_ms"] == 250

    def test_p95_ignores_rows_with_no_latency(self, db: Session) -> None:
        """A transport error records no latency. Treating NULL as 0 would drag
        the percentile down and make a failing provider look fast."""
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, latency=500)
        _log(db, latency=None, ok=False, error="ReadTimeout")

        assert analytics_service.didox_usage(db)["by_operation"][0]["p95_latency_ms"] == 500

    def test_p95_is_none_when_nothing_has_a_latency(self, db: Session) -> None:
        """None, not 0 — "we do not know" and "instant" are different claims."""
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, latency=None, ok=False, error="ReadTimeout")

        assert analytics_service.didox_usage(db)["by_operation"][0]["p95_latency_ms"] is None


@_requires_real_db
class TestProviderHealth:
    def test_both_providers_are_reported(self, db: Session) -> None:
        """E-IMZO is in the same table and was equally invisible."""
        from app.services import analytics_service  # noqa: PLC0415

        _log(db, provider="didox")
        _log(db, provider="eimzo", operation="verify_pkcs7")

        providers = {r["provider"] for r in analytics_service.provider_health(db)}
        assert providers == {"didox", "eimzo"}

    def test_success_rate_counts_failures(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        _log(db)
        _log(db)
        _log(db, ok=False, error="didox_5xx")

        health = analytics_service.provider_health(db)[0]
        assert health["success_pct"] == pytest.approx(66.7, abs=0.1)


@_requires_real_db
class TestAiUsage:
    def test_an_empty_database_reports_zero_rather_than_failing(self, db: Session) -> None:
        from app.services import analytics_service  # noqa: PLC0415

        usage = analytics_service.ai_usage(db, days=30)

        assert usage["has_data"] is False
        assert usage["by_purpose"] == []
        assert usage["total_calls"] == 0

    def test_a_report_row_is_counted_under_its_purpose(self, db: Session) -> None:
        """The report was the only LLM caller journalling nothing, which is why
        migration 0047 exists. This is the round trip."""
        from app.services import analytics_service  # noqa: PLC0415

        db.execute(
            sa.text(
                """
                INSERT INTO reports
                    (kind, period_start, period_end, title, content_md, data_snapshot,
                     status, generated_by, tokens_in, tokens_out, created_at)
                VALUES ('morning', current_date, current_date, 't', 'md', '{}'::jsonb,
                        'draft', 'claude-sonnet-4-5 v6', 4000, 6500, now())
                """
            )
        )
        db.commit()

        usage = analytics_service.ai_usage(db, days=30)
        report = next(r for r in usage["by_purpose"] if r["purpose"] == "report")

        assert (report["tokens_in"], report["tokens_out"]) == (4000, 6500)
        # `generated_by` is "<model> <prompt version>"; the model is the first word.
        assert any(m["model"] == "claude-sonnet-4-5" for m in usage["by_model"])

    def test_a_rule_based_report_contributes_no_tokens(self, db: Session) -> None:
        """`tokens_in IS NULL` means no call was attempted, which is different
        from a call that spent nothing — the union must not count it."""
        from app.services import analytics_service  # noqa: PLC0415

        db.execute(
            sa.text(
                """
                INSERT INTO reports
                    (kind, period_start, period_end, title, content_md, data_snapshot,
                     status, generated_by, created_at)
                VALUES ('morning', current_date, current_date, 't', 'md', '{}'::jsonb,
                        'draft', 'rule_based', now())
                """
            )
        )
        db.commit()

        assert analytics_service.ai_usage(db, days=30)["has_data"] is False

    def test_the_degradation_panel_counts_rule_based_reports(self, db: Session) -> None:
        """Which is exactly where a report with no tokens SHOULD appear."""
        from app.services import analytics_service  # noqa: PLC0415

        db.execute(
            sa.text(
                """
                INSERT INTO reports
                    (kind, period_start, period_end, title, content_md, data_snapshot,
                     status, generated_by, created_at)
                VALUES ('morning', current_date, current_date, 't', 'md', '{}'::jsonb,
                        'draft', 'rule_based', now())
                """
            )
        )
        db.commit()

        assert analytics_service.ai_degradation(db, days=30)["rule_based_reports"] == 1


@_requires_real_db
class TestCostPerOutcome:
    def test_nothing_produced_gives_none_not_zero(self, db: Session) -> None:
        """Dividing by zero would print an infinity; rounding it to 0 would read
        as "free". Neither is what "we verified nobody this month" means."""
        from app.services import analytics_service  # noqa: PLC0415

        result = analytics_service.cost_per_outcome(
            db, days=30, didox_spent_uzs=1000.0, by_purpose=[]
        )

        assert result["uzs_per_document"] is None
        assert result["tokens_per_news_article"] is None
