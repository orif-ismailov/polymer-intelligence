"""
End-to-end SQL for the Phase 8a news filter/search/sort surface, against a real
localhost test PostgreSQL. Same skip guard as test_catalog_search / test_relevance_service:
a developer-provisioned localhost DB named "test_polymer". Skips in CI (whose DB is
polymer_intelligence_test and whose conftest patch_env swaps DATABASE_URL) and when
unconfigured, so this self-migrating fixture never touches the CI/prod DB.

The pure Python (WHERE-builder, sort) is covered DB-free in test_news_articles_api.py;
this validates the raw JSONB SQL (jsonb_exists, LATERAL unnest, scope predicates) that
those unit tests can't reach.

Run against the dev stack's Postgres like:
    DATABASE_URL=postgresql+psycopg://pi_user:PASS@localhost:5432/test_polymer \
        uv run pytest tests/test_news_filter_sql_db.py -q
"""

from __future__ import annotations

import contextlib
import datetime
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command as alembic_command

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "News filter DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


def _news_ai(headline: str, *, category: str, country: str | None,
             importance: str, companies: list[str], products: list[str],
             summary: str, tags: list[str] | None = None,
             analysis: str | None = None, recommendation: str | None = None,
             language: str | None = None, i18n: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "news": {
            "headline": headline,
            "category": category,
            "tags": tags if tags is not None else [category],
            "country": country,
            "countries": [country] if country else [],
            "related_products": products,
            "companies": companies,
            "importance": importance,
            "market_impact": "negative",
            "summary": summary,
            "analysis": analysis,
            "recommendation": recommendation,
            "language": language,
            "i18n": i18n,
        },
        "confidence": 0.9,
    }


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def seeded_news(engine: sa.Engine):  # noqa: ANN201 — module fixture
    """Migrate a clean schema and insert news signals across two sources/countries."""
    # conftest.patch_env forces DATABASE_URL to a placeholder for the whole session, and
    # alembic's env.py reads settings.DATABASE_URL — point both at the real test DB.
    from app.core.config import settings  # noqa: PLC0415

    original_url = settings.DATABASE_URL
    try:
        settings.DATABASE_URL = _DB_URL
    except Exception:  # noqa: BLE001 — frozen settings: bypass validation
        object.__setattr__(settings, "DATABASE_URL", _DB_URL)

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")
    alembic_command.upgrade(alembic_cfg, "head")

    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from app.models.enums import PriceBasis, SignalKind, SourceKind  # noqa: PLC0415
    from app.models.signals import Signal  # noqa: PLC0415
    from app.models.sources import Source  # noqa: PLC0415

    now = datetime.datetime.now(tz=datetime.UTC)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        uz = Source(id=901, kind=SourceKind.rss, adapter="rss", name="UzPetroTG", country="UZ")
        world = Source(id=902, kind=SourceKind.rss, adapter="rss", name="OilWorld", country="RU")
        session.add_all([uz, world])
        session.flush()

        def _sig(sid: int, ai: dict[str, object], minutes_ago: int) -> Signal:
            return Signal(
                kind=SignalKind.news, source_id=sid, product_id=None,
                grade_text=ai["news"]["headline"], region=ai["news"]["country"],  # type: ignore[index]
                price_basis=PriceBasis.unknown, status="new",
                event_at=now - datetime.timedelta(minutes=minutes_ago), ai=ai,
            )

        session.add_all([
            _sig(901, _news_ai(
                "Shurtan останавливает PP-линию на ремонт", category="plant_shutdown",
                country="Uzbekistan", importance="high", companies=["Shurtan GCC"],
                products=["PP"], summary="Плановый ремонт сократит выпуск PP.",
                tags=["plant_shutdown", "production"], language="ru",
                analysis="Ремонт сократит предложение PP на внутреннем рынке.",
                recommendation="Следите за ценами PP.",
                i18n={"uz": {"headline": "Shurtan PP liniyasini ta'mirlash uchun to'xtatadi",
                             "summary": "Rejali ta'mir PP ishlab chiqarishni kamaytiradi.",
                             "recommendation": "PP narxlarini kuzating."},
                      "en": {"headline": "Shurtan halts PP line for maintenance"}}), 10),
            _sig(901, _news_ai(
                "Обзор рынка полимеров Узбекистана", category="market_analysis",
                country="Uzbekistan", importance="low", companies=[],
                products=["HDPE"], summary="Спрос стабилен."), 30),
            _sig(902, _news_ai(
                "SIBUR expands ethylene capacity", category="new_projects",
                country="Russia", importance="medium", companies=["SIBUR"],
                products=["ethylene"], summary="New capacity pressures prices."), 20),
            _sig(902, _news_ai(
                "Brent crude edges higher on OPEC", category="oil",
                country=None, importance="medium", companies=[],
                products=[], summary="Feedstock costs may rise."), 40),
        ])
        session.commit()

    yield engine

    with session_factory() as session:
        session.execute(sa.text("DELETE FROM signals WHERE source_id IN (901, 902)"))
        session.execute(sa.text("DELETE FROM sources WHERE id IN (901, 902)"))
        session.commit()
    with contextlib.suppress(Exception):
        settings.DATABASE_URL = original_url


def _headlines(cards: list[dict[str, object]]) -> list[str]:
    return [str(c["headline"]) for c in cards]


@_requires_real_db
class TestNewsFilterSqlDb:
    def _session(self, engine: sa.Engine):  # noqa: ANN202
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        return sessionmaker(bind=engine)()

    def test_no_filter_returns_all_news(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            cards = news_service.list_news_articles(s, days=1)
        assert len(cards) == 4
        # default order is importance→recency: the 'high' shutdown leads
        assert cards[0]["importance"] == "high"

    def test_scope_uzbekistan(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            cards = news_service.list_news_articles(s, days=1, scope="uzbekistan")
        assert {c["country"] for c in cards} == {"Uzbekistan"}
        assert len(cards) == 2

    def test_scope_global_excludes_uz(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            cards = news_service.list_news_articles(s, days=1, scope="global")
        assert "Uzbekistan" not in {c["country"] for c in cards}
        assert len(cards) == 2

    def test_scope_producers_matches_companies_or_category(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            cards = news_service.list_news_articles(s, days=1, scope="producers")
        heads = _headlines(cards)
        assert any("Shurtan" in h for h in heads)   # named company
        assert any("SIBUR" in h for h in heads)     # company + new_projects
        assert not any("Brent" in h for h in heads)  # no company, non-producer category

    def test_search_matches_headline_and_company(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            by_head = news_service.list_news_articles(s, days=1, q="shurtan")
            by_company = news_service.list_news_articles(s, days=1, q="sibur")
        assert _headlines(by_head) == ["Shurtan останавливает PP-линию на ремонт"]
        assert _headlines(by_company) == ["SIBUR expands ethylene capacity"]

    def test_filter_category_matches_primary_or_tag(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            primary = news_service.list_news_articles(s, days=1, category="oil")
            via_tag = news_service.list_news_articles(s, days=1, category="production")
        assert _headlines(primary) == ["Brent crude edges higher on OPEC"]
        assert any("Shurtan" in h for h in _headlines(via_tag))  # 'production' is a tag

    def test_filter_country_and_importance(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            ru = news_service.list_news_articles(s, days=1, country="Russia")
            high = news_service.list_news_articles(s, days=1, importance="high")
        assert _headlines(ru) == ["SIBUR expands ethylene capacity"]
        assert _headlines(high) == ["Shurtan останавливает PP-линию на ремонт"]

    def test_sort_newest(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            cards = news_service.list_news_articles(s, days=1, sort="newest")
        # inserted 10/20/30/40 min ago → newest first is the 10-min shutdown
        assert cards[0]["headline"] == "Shurtan останавливает PP-линию на ремонт"

    def test_localizes_display_fields_to_lang(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            uz = news_service.list_news_articles(s, days=1, q="shurtan", lang="uz")
            canonical = news_service.list_news_articles(s, days=1, q="shurtan")
            detail_uz = news_service.get_news_article(s, int(uz[0]["id"]), lang="uz")
        assert uz[0]["headline"] == "Shurtan PP liniyasini ta'mirlash uchun to'xtatadi"
        assert uz[0]["recommendation"] == "PP narxlarini kuzating."
        # analysis had no uz translation → falls back to the canonical (ru) text
        assert uz[0]["analysis"] == "Ремонт сократит предложение PP на внутреннем рынке."
        assert canonical[0]["headline"] == "Shurtan останавливает PP-линию на ремонт"
        assert detail_uz is not None
        assert detail_uz["headline"] == "Shurtan PP liniyasini ta'mirlash uchun to'xtatadi"

    def test_filter_options_facets(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        with self._session(seeded_news) as s:
            opts = news_service.list_news_filter_options(s, days=1)
        cats = {f["value"] for f in opts["categories"]}  # type: ignore[union-attr]
        countries = {f["value"] for f in opts["countries"]}  # type: ignore[union-attr]
        companies = {f["value"] for f in opts["companies"]}  # type: ignore[union-attr]
        products = {f["value"] for f in opts["products"]}  # type: ignore[union-attr]
        assert {"plant_shutdown", "oil", "new_projects", "market_analysis"} <= cats
        assert {"Uzbekistan", "Russia"} <= countries
        assert {"Shurtan GCC", "SIBUR"} <= companies
        assert {"PP", "HDPE", "ethylene"} <= products


def _open(engine: sa.Engine):  # noqa: ANN202
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    return sessionmaker(bind=engine)()


@_requires_real_db
class TestReportSectionsDb:
    def test_three_section_bucketing(self, seeded_news: sa.Engine) -> None:
        from app.services import report_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            sections = report_service._snapshot_sections(s)
        uz = _headlines(list(sections["uzbekistan"]))  # type: ignore[arg-type]
        gl = _headlines(list(sections["global"]))  # type: ignore[arg-type]
        pr = _headlines(list(sections["producers"]))  # type: ignore[arg-type]
        assert any("Shurtan" in h for h in uz)
        assert any("SIBUR" in h for h in gl)
        assert not any("SIBUR" in h for h in uz)  # Russia story not in the UZ section
        assert any("Shurtan" in h for h in pr) and any("SIBUR" in h for h in pr)  # both name a company
        # sections are localized to ru and carry no raw i18n block
        assert all("i18n" not in c for c in sections["uzbekistan"])  # type: ignore[union-attr]


@_requires_real_db
class TestSettingsDb:
    def test_defaults_then_override(self, seeded_news: sa.Engine) -> None:
        from app.services import settings_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            assert settings_service.get(s, "news_ai_enabled") is True  # default
            assert settings_service.get(s, "news_require_approval") is False
            settings_service.set_many(s, {"news_require_approval": True}, staff_user_id=None)
            s.commit()
        with _open(seeded_news) as s:
            assert settings_service.get(s, "news_require_approval") is True  # persisted
            allsettings = {r["key"]: r for r in settings_service.get_all(s)}
            assert allsettings["news_require_approval"]["is_overridden"] is True
            assert allsettings["news_ai_enabled"]["is_overridden"] is False
            # reset so other tests see the default
            settings_service.set_many(s, {"news_require_approval": False}, staff_user_id=None)
            s.commit()

    def test_unknown_key_raises(self, seeded_news: sa.Engine) -> None:
        import pytest as _pytest  # noqa: PLC0415

        from app.services import settings_service  # noqa: PLC0415

        with _open(seeded_news) as s, _pytest.raises(KeyError):
            settings_service.get(s, "does_not_exist")

    def test_get_all_serializes_through_response_schema(self, seeded_news: sa.Engine) -> None:
        """Regression for the /admin/settings 500: every spec's get_all() output must
        validate through SettingItem (the int refresh-interval broke a bool|str union)."""
        from app.schemas.admin_settings import SettingItem  # noqa: PLC0415
        from app.services import settings_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            by_key = {
                i.key: i for i in (SettingItem.model_validate(r) for r in settings_service.get_all(s))
            }
        assert isinstance(by_key["news_refresh_interval_minutes"].value, int)
        assert isinstance(by_key["news_ai_enabled"].value, bool)
        assert isinstance(by_key["llm_extract_model"].value, str)

    def test_int_setting_clamped(self, seeded_news: sa.Engine) -> None:
        from app.services import settings_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            assert settings_service.get(s, "news_refresh_interval_minutes") == 60  # default
            settings_service.set_many(s, {"news_refresh_interval_minutes": 3}, staff_user_id=None)
            s.commit()
            assert settings_service.get(s, "news_refresh_interval_minutes") == 5  # clamped to min
            settings_service.set_many(s, {"news_refresh_interval_minutes": "120"}, staff_user_id=None)
            s.commit()
            assert settings_service.get(s, "news_refresh_interval_minutes") == 120  # string coerced
            # reset for isolation
            settings_service.set_many(s, {"news_refresh_interval_minutes": 60}, staff_user_id=None)
            s.commit()


@_requires_real_db
class TestApprovalDb:
    def _insert_pending(self, engine: sa.Engine) -> int:
        import datetime as _dt  # noqa: PLC0415

        from app.models.enums import PriceBasis, SignalKind  # noqa: PLC0415
        from app.models.signals import Signal  # noqa: PLC0415

        with _open(engine) as s:
            sig = Signal(
                kind=SignalKind.news, source_id=901, price_basis=PriceBasis.unknown,
                grade_text="Pending: Uzbek PP capacity add", region="Uzbekistan",
                status="new", event_at=_dt.datetime.now(tz=_dt.UTC),
                ai={"news": {"headline": "Pending: Uzbek PP capacity add", "category": "new_projects",
                             "importance": "high", "country": "Uzbekistan", "companies": ["NewCo"],
                             "related_products": ["PP"], "summary": "Awaiting approval.",
                             "approval": "pending"}},
            )
            s.add(sig)
            s.commit()
            return int(sig.id)

    def test_pending_hidden_until_approved(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        sig_id = self._insert_pending(seeded_news)
        with _open(seeded_news) as s:
            visible = news_service.list_news_articles(s, days=1, q="capacity add")
            pending = news_service.list_pending_news(s)
            assert not any(c["id"] == sig_id for c in visible)  # hidden from public feed
            assert any(c["id"] == sig_id for c in pending)       # shown in the review queue
            assert news_service.get_news_article(s, sig_id) is None  # detail 404s while pending

            news_service.set_news_approval(s, sig_id, approved=True)
            s.commit()

        with _open(seeded_news) as s:
            visible2 = news_service.list_news_articles(s, days=1, q="capacity add")
            assert any(c["id"] == sig_id for c in visible2)       # now public
            assert news_service.get_news_article(s, sig_id) is not None

    def test_reject_hides_permanently(self, seeded_news: sa.Engine) -> None:
        from app.services import news_service  # noqa: PLC0415

        sig_id = self._insert_pending(seeded_news)
        with _open(seeded_news) as s:
            news_service.set_news_approval(s, sig_id, approved=False)
            s.commit()
        with _open(seeded_news) as s:
            visible = news_service.list_news_articles(s, days=1, q="capacity add")
            assert not any(c["id"] == sig_id for c in visible)
            assert not any(c["id"] == sig_id for c in news_service.list_pending_news(s))


@_requires_real_db
class TestBreakingNewsDb:
    def test_pending_then_mark_excludes(self, seeded_news: sa.Engine) -> None:
        from app.services import report_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            pending = report_service.pending_breaking_news(s, minutes=180)
            heads = [str(p["card"]["headline"]) for p in pending]  # type: ignore[index]
            assert any("Shurtan" in h for h in heads)  # the only 'high' story
            assert not any("SIBUR" in h for h in heads)  # medium importance → not breaking

            ids = [i for p in pending for i in p["ids"]]  # type: ignore[union-attr]
            report_service.mark_breaking_pushed(s, ids)
            s.commit()

            again = report_service.pending_breaking_news(s, minutes=180)
        assert not any("Shurtan" in str(p["card"]["headline"]) for p in again)  # type: ignore[index]


@_requires_real_db
class TestRssFetchDueDb:
    def test_due_when_never_fetched_then_respects_interval(self, seeded_news: sa.Engine) -> None:
        import datetime as _dt  # noqa: PLC0415

        from app.tasks.ingest_rss import rss_fetch_due  # noqa: PLC0415

        # seeded rss sources 901/902 start with last_fetch_at = NULL → always due
        with _open(seeded_news) as s:
            assert rss_fetch_due(s, 60) is True

            now = _dt.datetime.now(tz=_dt.UTC)
            s.execute(sa.text("UPDATE sources SET last_fetch_at = :t WHERE id IN (901, 902)"), {"t": now})
            s.commit()
            assert rss_fetch_due(s, 60) is False  # fetched just now → not due

            stale = now - _dt.timedelta(minutes=90)
            s.execute(sa.text("UPDATE sources SET last_fetch_at = :t WHERE id IN (901, 902)"), {"t": stale})
            s.commit()
            assert rss_fetch_due(s, 60) is True  # 90 min old, interval 60 → due
            assert rss_fetch_due(s, 120) is False  # interval 120 → not yet


@_requires_real_db
class TestSourceGroupsDb:
    def test_assign_list_and_clear(self, seeded_news: sa.Engine) -> None:
        from app.services import source_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            assert source_service.set_source_group(s, 901, "Uzbek news") is True
            assert source_service.set_source_group(s, 902, "Global news") is True
            s.commit()

            groups = {g["group"]: g for g in source_service.list_source_groups(s)}
            assert groups["Uzbek news"]["total"] == 1
            assert groups["Global news"]["active"] == 1

            brief = {b["id"]: b for b in source_service.list_sources_brief(s)}
            assert brief[901]["group_name"] == "Uzbek news"

            assert source_service.set_source_group(s, 901, "  ") is True  # blank clears
            s.commit()
            assert next(b for b in source_service.list_sources_brief(s) if b["id"] == 901)["group_name"] is None

    def test_missing_source_returns_false(self, seeded_news: sa.Engine) -> None:
        from app.services import source_service  # noqa: PLC0415

        with _open(seeded_news) as s:
            assert source_service.set_source_group(s, 99999, "X") is False
