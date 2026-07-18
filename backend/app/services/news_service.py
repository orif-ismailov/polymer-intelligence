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
