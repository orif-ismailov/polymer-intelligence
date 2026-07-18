"""Tests for the News-Intelligence extraction schema (parsing.news_schemas)."""

from __future__ import annotations

import pytest


def test_relevant_article_keeps_fields() -> None:
    from parsing.news_schemas import NewsArticle, NewsImportance, NewsMarketImpact

    a = NewsArticle(
        is_relevant=True,
        headline="Shurtan GCC raises PP prices",
        category="polypropylene",
        tags=["market_prices", "polymers"],
        country="Uzbekistan",
        related_products=["PP"],
        companies=["Shurtan GCC"],
        importance="high",
        market_impact="positive",
        summary="Domestic PP offers move up; buyers should expect firmer quotes.",
        confidence=0.9,
    )
    assert a.importance is NewsImportance.HIGH
    assert a.market_impact is NewsMarketImpact.POSITIVE
    assert a.related_products == ["PP"]
    assert a.tags == ["market_prices", "polymers"]


def test_irrelevant_article_is_emptied() -> None:
    """is_relevant=False ⇒ classification payload is cleared (structural firewall)."""
    from parsing.news_schemas import NewsArticle

    a = NewsArticle(
        is_relevant=False,
        headline="Celebrity gossip",
        category="polymers",
        tags=["oil"],
        country="Russia",
        related_products=["PP"],
        companies=["X"],
        importance="high",
        market_impact="positive",
        summary="irrelevant",
        confidence=0.8,
    )
    assert a.headline is None
    assert a.category is None
    assert a.tags == []
    assert a.related_products == []
    assert a.companies == []
    assert a.importance is None
    assert a.market_impact is None
    assert a.summary is None


def test_summary_capped_at_150_words() -> None:
    from parsing.news_schemas import NewsArticle

    long_summary = " ".join(f"word{i}" for i in range(300))
    a = NewsArticle(is_relevant=True, summary=long_summary, confidence=0.5)
    assert a.summary is not None
    assert len(a.summary.split()) == 150


def test_confidence_out_of_range_rejected() -> None:
    from pydantic import ValidationError

    from parsing.news_schemas import NewsArticle

    with pytest.raises(ValidationError):
        NewsArticle(is_relevant=True, confidence=1.5)


def test_invalid_importance_rejected() -> None:
    from pydantic import ValidationError

    from parsing.news_schemas import NewsArticle

    with pytest.raises(ValidationError):
        NewsArticle(is_relevant=True, importance="critical", confidence=0.5)  # type: ignore[arg-type]
