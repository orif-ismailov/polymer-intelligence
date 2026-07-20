"""
News signal construction (Phase 7b).

Turns a NewsArticle (from parsing.news_extractor) into a Signal with kind='news',
storing the rich classification under signals.ai JSONB (Option A — no schema migration).
The daily report (_snapshot_news), the live feed, and the webapp read news signals; the
`ai.news` block carries headline/category/importance/market_impact/summary etc.

grade_text holds the headline so the news shows up in the feed's product column; region
holds the country; product_id is best-effort resolved from the article's related_products
so news can be filtered per product. The service performs no commit (caller owns it).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import PriceBasis, SignalKind
from app.models.signals import Signal
from app.services.news_dedup import cluster_articles
from app.services.relevance_service import match_product

if TYPE_CHECKING:
    from app.models.sources import RawItem
    from parsing.news_schemas import NewsArticle


def _resolve_product_id(session: Session, related_products: list[str]) -> int | None:
    """Best-effort: map the first recognizable product code to a product_id (else None)."""
    for code in related_products:
        product_id = match_product(session, code)
        if product_id is not None:
            return product_id
    return None


def create_news_signal_from_article(
    session: Session,
    raw_item: RawItem,
    article: NewsArticle,
    journal: dict[str, object],
    *,
    needs_review: bool,
) -> Signal:
    """Build a kind='news' Signal from a classified NewsArticle. Does NOT commit."""
    now_iso = datetime.datetime.now(tz=datetime.UTC).isoformat()
    event_at = raw_item.event_at or datetime.datetime.now(tz=datetime.UTC)

    product_id = _resolve_product_id(session, article.related_products)

    ai_data: dict[str, object] = {
        "news": {
            "headline": article.headline,
            "category": article.category,
            "tags": article.tags,
            "country": article.country,
            "countries": article.countries,
            "related_products": article.related_products,
            "companies": article.companies,
            "importance": article.importance.value if article.importance else None,
            "market_impact": article.market_impact.value if article.market_impact else None,
            "summary": article.summary,
            "analysis": article.analysis,
            "recommendation": article.recommendation,
            "language": article.language,
            "i18n": article.i18n.model_dump(exclude_none=True) if article.i18n else None,
        },
        "confidence": article.confidence,
        "needs_review": needs_review,
        "model": journal.get("model"),
        "prompt_version": journal.get("prompt_version"),
        "scored_at": now_iso,
    }

    return Signal(
        kind=SignalKind.news,
        source_id=raw_item.source_id,
        raw_item_id=raw_item.id,
        product_id=product_id,
        grade_id=None,
        grade_text=article.headline,        # headline surfaces in the feed's product column
        volume=None,
        volume_unit="MT",
        price=None,
        currency=None,
        price_basis=PriceBasis.unknown,
        region=article.country,
        destination=None,
        counterparty_id=None,
        counterparty_text=None,
        status="new",
        event_at=event_at,
        ai=ai_data,
    )


# ── Reads (Phase 7e — Mini-App news cards) ─────────────────────────────────────────
# The webapp News tab surfaces individual classified articles as cards, distinct from
# the whole-day digest reports. Cards are read straight from the kind='news' signals
# and their ai.news block, ranked by importance then recency.


def _article_card(row: sa.engine.RowMapping) -> dict[str, object]:
    """Map a news signal row (with its ai JSONB) to a card dict for the webapp."""
    ai = row["ai"] if isinstance(row["ai"], dict) else {}
    news_raw = ai.get("news")
    news = news_raw if isinstance(news_raw, dict) else {}
    event_at = row["event_at"]
    i18n = news.get("i18n")
    return {
        "id": int(row["id"]),
        "headline": str(news.get("headline") or ""),
        "category": news.get("category"),
        "importance": news.get("importance"),
        "market_impact": news.get("market_impact"),
        "summary": news.get("summary"),
        "analysis": news.get("analysis"),
        "recommendation": news.get("recommendation"),
        "language": news.get("language"),
        "country": news.get("country") or row["country"],
        "countries": [str(c) for c in (news.get("countries") or [])],
        "companies": [str(c) for c in (news.get("companies") or [])],
        "related_products": [str(p) for p in (news.get("related_products") or [])],
        "source_name": str(row["source_name"]) if row["source_name"] else None,
        "published_at": event_at.isoformat() if event_at is not None else None,
        "image_url": None,  # reserved — no image extracted yet
        # Raw ru/uz/en variants; consumed by _localize, then dropped by the schema.
        "i18n": i18n if isinstance(i18n, dict) else None,
    }


# ── Per-language localization (Phase 8b/8f) ─────────────────────────────────────────
# News is classified once and translated at ingest into ru/uz/en (ai.news.i18n). Cards
# are localized to the caller's language just before display; clustering/sorting run on
# the canonical (source-language) fields, so localization never affects dedup order.

_LOCALIZED_FIELDS = ("headline", "summary", "analysis", "recommendation")


def _localize(card: dict[str, object], lang: str | None) -> dict[str, object]:
    """Override display fields from ai.news.i18n[lang] when a translation exists."""
    i18n = card.get("i18n")
    if not lang or not isinstance(i18n, dict):
        return card
    loc = i18n.get(lang)
    if not isinstance(loc, dict):
        return card
    for field in _LOCALIZED_FIELDS:
        value = loc.get(field)
        if value:
            card[field] = value
    return card


# Fetch a generous window of recent news so clustering has enough to merge against;
# callers then keep only as many representative stories as they need.
_CLUSTER_ROW_CAP = 200


def _recent_article_rows(
    session: Session,
    *,
    days: int,
    cap: int = _CLUSTER_ROW_CAP,
    extra_where: list[str] | None = None,
    extra_params: dict[str, object] | None = None,
) -> list[sa.engine.RowMapping]:
    """Recent kind='news' rows, ranked importance→recency (for card mapping + clustering).

    `extra_where`/`extra_params` append filter clauses (search/scope/category/…). The
    clause strings are built from static SQL only (see `_news_filter_sql`); every user
    value travels as a bound param, so the f-string interpolation is injection-safe.
    """
    where = [
        "s.kind = 'news'",
        "s.ai -> 'news' IS NOT NULL",
        "s.event_at >= now() - make_interval(days => :days)",
    ]
    params: dict[str, object] = {"days": days, "cap": cap}
    if extra_where:
        where.extend(extra_where)
    if extra_params:
        params.update(extra_params)
    sql = f"""
        SELECT s.id AS id, s.event_at AS event_at, s.ai AS ai,
               src.name AS source_name, src.country AS country
        FROM signals s
        JOIN sources src ON src.id = s.source_id
        WHERE {" AND ".join(where)}
        ORDER BY (
            CASE s.ai->'news'->>'importance'
                WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0
            END
        ) DESC, s.event_at DESC
        LIMIT :cap
    """
    return list(session.execute(sa.text(sql), params).mappings().all())


def _source_refs(members: list[dict[str, object]]) -> list[dict[str, object]]:
    """Source references for a cluster, original (earliest published) first."""
    refs: list[dict[str, object]] = [
        {"id": m["id"], "name": m.get("source_name"), "published_at": m.get("published_at")}
        for m in members
    ]
    refs.sort(key=lambda r: (r["published_at"] is None, str(r["published_at"] or "")))
    return refs


def _merge_cluster(members: list[dict[str, object]]) -> dict[str, object]:
    """Collapse a same-story cluster into its representative card + merged sources."""
    rep = dict(members[0])
    rep["sources"] = _source_refs(members)
    rep["merged_count"] = len(members)
    return rep


# ── Filtering / search / sort (Phase 8a) ───────────────────────────────────────────
# The webapp News tab drives All/Uzbekistan/Global/Producers tabs, a search box, per-
# facet filters, and a sort selector. Filters push into SQL (so the row cap applies to
# the matching set); the final sort is applied to the merged representative cards.

# "Producers" = news that names a company/plant, or sits in a producer-side category.
_PRODUCER_CATEGORIES: tuple[str, ...] = (
    "production", "plant_shutdown", "maintenance", "refineries",
    "factories", "new_projects", "investment", "petrochemicals",
)
_PRODUCER_CATEGORIES_SQL = ", ".join(f"'{c}'" for c in _PRODUCER_CATEGORIES)
_UZ_COUNTRY_VALUES = "('uzbekistan', 'uz', 'узбекистан')"
_UZ_MATCH = f"lower(coalesce(nullif(s.ai->'news'->>'country', ''), src.country, '')) IN {_UZ_COUNTRY_VALUES}"


def _news_filter_sql(
    *,
    q: str | None,
    scope: str | None,
    category: str | None,
    country: str | None,
    company: str | None,
    product: str | None,
    importance: str | None,
    source_id: int | None,
) -> tuple[list[str], dict[str, object]]:
    """Build (where-clauses, bound-params) for the news card query. All values bound."""
    clauses: list[str] = []
    params: dict[str, object] = {}
    if q:
        params["q"] = f"%{q}%"
        clauses.append(
            "(s.ai->'news'->>'headline' ILIKE :q"
            " OR s.ai->'news'->>'summary' ILIKE :q"
            " OR s.ai->'news'->>'category' ILIKE :q"
            " OR (s.ai->'news'->'companies')::text ILIKE :q"
            " OR (s.ai->'news'->'related_products')::text ILIKE :q)"
        )
    if scope == "uzbekistan":
        clauses.append(_UZ_MATCH)
    elif scope == "global":
        clauses.append(f"NOT ({_UZ_MATCH})")
    elif scope == "producers":
        clauses.append(
            "((jsonb_typeof(s.ai->'news'->'companies') = 'array'"
            " AND jsonb_array_length(s.ai->'news'->'companies') > 0)"
            f" OR s.ai->'news'->>'category' IN ({_PRODUCER_CATEGORIES_SQL}))"
        )
    if category:
        params["category"] = category
        clauses.append(
            "(s.ai->'news'->>'category' = :category"
            " OR jsonb_exists(s.ai->'news'->'tags', :category))"
        )
    if country:
        params["country"] = country
        clauses.append(
            "(lower(s.ai->'news'->>'country') = lower(:country)"
            " OR lower(src.country) = lower(:country))"
        )
    if company:
        params["company"] = f"%{company}%"
        clauses.append("(s.ai->'news'->'companies')::text ILIKE :company")
    if product:
        params["product"] = f"%{product}%"
        clauses.append("(s.ai->'news'->'related_products')::text ILIKE :product")
    if importance:
        params["importance"] = importance
        clauses.append("s.ai->'news'->>'importance' = :importance")
    if source_id is not None:
        params["source_id"] = source_id
        clauses.append("s.source_id = :source_id")
    return clauses, params


_IMPORTANCE_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}
_SORT_LAST = "￿"  # sorts after any real value, so empties land last on asc sorts


def _rank(card: dict[str, object]) -> int:
    return _IMPORTANCE_RANK.get(str(card.get("importance") or ""), 0)


def _first_lower(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0]).lower()
    return _SORT_LAST


def _text_lower(value: object) -> str:
    return str(value).lower() if value else _SORT_LAST


def _sort_cards(cards: list[dict[str, object]], sort: str | None) -> list[dict[str, object]]:
    """Order merged cards by the requested key. Default (importance) keeps SQL order."""
    if sort == "newest":
        return sorted(cards, key=lambda c: str(c.get("published_at") or ""), reverse=True)
    if sort == "category":
        return sorted(cards, key=lambda c: (_text_lower(c.get("category")), -_rank(c)))
    if sort == "country":
        return sorted(cards, key=lambda c: (_text_lower(c.get("country")), -_rank(c)))
    if sort == "company":
        return sorted(cards, key=lambda c: (_first_lower(c.get("companies")), -_rank(c)))
    if sort == "products":
        return sorted(cards, key=lambda c: (_first_lower(c.get("related_products")), -_rank(c)))
    return cards  # None / "importance" — already importance→recency from SQL


def list_news_articles(
    session: Session,
    *,
    limit: int = 30,
    days: int = 7,
    q: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    country: str | None = None,
    company: str | None = None,
    product: str | None = None,
    importance: str | None = None,
    source_id: int | None = None,
    sort: str | None = None,
    lang: str | None = None,
) -> list[dict[str, object]]:
    """Ranked, cross-source-deduped news cards from the last `days`, with filters.

    Same-story items from multiple sources collapse into one representative card; the
    others are attached under `sources` (with `merged_count`). Filters (search/scope/
    category/country/company/product/importance/source) apply in SQL before clustering;
    the merged cards are then ordered by `sort` and localized to `lang`. ≤`limit` stories.
    """
    clauses, params = _news_filter_sql(
        q=q, scope=scope, category=category, country=country,
        company=company, product=product, importance=importance, source_id=source_id,
    )
    rows = _recent_article_rows(session, days=days, extra_where=clauses, extra_params=params)
    cards = [_article_card(r) for r in rows if r["ai"] and isinstance(r["ai"], dict)]
    clusters = cluster_articles(cards)
    merged = [_merge_cluster(members) for members in clusters]
    return [_localize(c, lang) for c in _sort_cards(merged, sort)[:limit]]


def get_news_article(
    session: Session, signal_id: int, *, lang: str | None = None
) -> dict[str, object] | None:
    """A single news card plus its detail fields (original body + source link).

    The article's cluster siblings (the same story reported elsewhere) are attached
    under `sources`, so the detail view can cite every source and the original.
    Display fields are localized to `lang` when a translation exists.
    """
    row = (
        session.execute(
            sa.text(
                """
                SELECT s.id AS id, s.event_at AS event_at, s.ai AS ai,
                       src.name AS source_name, src.country AS country,
                       ri.content AS body,
                       COALESCE(
                           ri.payload ->> 'url', ri.payload ->> 'link',
                           ri.payload ->> 'message_url', ri.payload ->> 'source_url',
                           src.url
                       ) AS source_url
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                LEFT JOIN raw_items ri ON ri.id = s.raw_item_id
                WHERE s.id = :signal_id
                  AND s.kind = 'news'
                  AND s.ai -> 'news' IS NOT NULL
                """
            ),
            {"signal_id": signal_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    card = _article_card(row)
    body = row["body"]
    card["body"] = str(body).strip() if body else None
    card["source_url"] = str(row["source_url"]) if row["source_url"] else None

    # Find this article's cluster among recent news to list every reporting source.
    sib_rows = _recent_article_rows(session, days=14, cap=300)
    sib_cards = [_article_card(r) for r in sib_rows if r["ai"] and isinstance(r["ai"], dict)]
    if all(c["id"] != signal_id for c in sib_cards):  # target older than the window
        sib_cards.append(_article_card(row))
    members = next(
        (cl for cl in cluster_articles(sib_cards) if any(m["id"] == signal_id for m in cl)),
        [_article_card(row)],
    )
    card["sources"] = _source_refs(members)
    card["merged_count"] = len(members)
    return _localize(card, lang)


# ── Filter options (Phase 8a) ──────────────────────────────────────────────────────
# Powers the webapp filter selectors: which categories/countries/companies/products
# actually occur in recent news, with counts, so the UI only offers live facets.


def _facet_rows(session: Session, sql: str, days: int) -> list[dict[str, object]]:
    rows = session.execute(sa.text(sql), {"days": days}).mappings().all()
    return [{"value": str(r["value"]), "count": int(r["count"])} for r in rows]


def list_news_filter_options(session: Session, *, days: int = 30) -> dict[str, object]:
    """Distinct categories/countries/companies/products in recent news, with counts."""
    scalar_base = (
        "FROM signals s JOIN sources src ON src.id = s.source_id "
        "WHERE s.kind = 'news' AND s.ai -> 'news' IS NOT NULL "
        "AND s.event_at >= now() - make_interval(days => :days)"
    )
    categories = _facet_rows(
        session,
        "SELECT s.ai->'news'->>'category' AS value, count(*) AS count "
        f"{scalar_base} AND coalesce(s.ai->'news'->>'category', '') <> '' "
        "GROUP BY 1 ORDER BY count DESC, value ASC LIMIT 60",
        days,
    )
    countries = _facet_rows(
        session,
        "SELECT coalesce(nullif(s.ai->'news'->>'country', ''), src.country) AS value, count(*) AS count "
        f"{scalar_base} AND coalesce(nullif(s.ai->'news'->>'country', ''), src.country) IS NOT NULL "
        "GROUP BY 1 ORDER BY count DESC, value ASC LIMIT 60",
        days,
    )
    # Companies/products live in JSONB arrays — unnest with LATERAL (WHERE before it).
    array_where = (
        "WHERE s.kind = 'news' AND s.ai -> 'news' IS NOT NULL "
        "AND s.event_at >= now() - make_interval(days => :days)"
    )
    companies = _facet_rows(
        session,
        "SELECT elem AS value, count(*) AS count FROM signals s "
        "CROSS JOIN LATERAL jsonb_array_elements_text(s.ai->'news'->'companies') AS elem "
        f"{array_where} AND jsonb_typeof(s.ai->'news'->'companies') = 'array' "
        "GROUP BY 1 ORDER BY count DESC, value ASC LIMIT 50",
        days,
    )
    products = _facet_rows(
        session,
        "SELECT elem AS value, count(*) AS count FROM signals s "
        "CROSS JOIN LATERAL jsonb_array_elements_text(s.ai->'news'->'related_products') AS elem "
        f"{array_where} AND jsonb_typeof(s.ai->'news'->'related_products') = 'array' "
        "GROUP BY 1 ORDER BY count DESC, value ASC LIMIT 50",
        days,
    )
    return {
        "categories": categories,
        "countries": countries,
        "companies": companies,
        "products": products,
    }
