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
            "related_products": article.related_products,
            "companies": article.companies,
            "importance": article.importance.value if article.importance else None,
            "market_impact": article.market_impact.value if article.market_impact else None,
            "summary": article.summary,
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
    return {
        "id": int(row["id"]),
        "headline": str(news.get("headline") or ""),
        "category": news.get("category"),
        "importance": news.get("importance"),
        "market_impact": news.get("market_impact"),
        "summary": news.get("summary"),
        "country": news.get("country") or row["country"],
        "companies": [str(c) for c in (news.get("companies") or [])],
        "related_products": [str(p) for p in (news.get("related_products") or [])],
        "source_name": str(row["source_name"]) if row["source_name"] else None,
        "published_at": event_at.isoformat() if event_at is not None else None,
        "image_url": None,  # reserved — no image extracted yet
    }


def list_news_articles(session: Session, *, limit: int = 30, days: int = 7) -> list[dict[str, object]]:
    """Ranked news cards from the last `days` (importance, then recency)."""
    rows = (
        session.execute(
            sa.text(
                """
                SELECT s.id AS id, s.event_at AS event_at, s.ai AS ai,
                       src.name AS source_name, src.country AS country
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                WHERE s.kind = 'news'
                  AND s.ai -> 'news' IS NOT NULL
                  AND s.event_at >= now() - make_interval(days => :days)
                ORDER BY (
                    CASE s.ai->'news'->>'importance'
                        WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0
                    END
                ) DESC, s.event_at DESC
                LIMIT :limit
                """
            ),
            {"days": days, "limit": limit},
        )
        .mappings()
        .all()
    )
    return [_article_card(r) for r in rows if r["ai"] and isinstance(r["ai"], dict)]


def get_news_article(session: Session, signal_id: int) -> dict[str, object] | None:
    """A single news card plus its detail fields (original body + source link)."""
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
    return card
