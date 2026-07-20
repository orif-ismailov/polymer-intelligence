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


def test_summary_capped_at_120_words() -> None:
    from parsing.news_schemas import NewsArticle

    long_summary = " ".join(f"word{i}" for i in range(300))
    a = NewsArticle(is_relevant=True, summary=long_summary, confidence=0.5)
    assert a.summary is not None
    assert len(a.summary.split()) == 120


def test_analysis_and_recommendation_capped() -> None:
    from parsing.news_schemas import NewsArticle

    a = NewsArticle(
        is_relevant=True,
        analysis=" ".join(f"w{i}" for i in range(400)),
        recommendation=" ".join(f"r{i}" for i in range(100)),
        confidence=0.5,
    )
    assert a.analysis is not None and len(a.analysis.split()) == 160
    assert a.recommendation is not None and len(a.recommendation.split()) == 40


def test_translations_and_new_fields_kept_when_relevant() -> None:
    from parsing.news_schemas import NewsArticle, NewsI18n, NewsLocalized

    a = NewsArticle(
        is_relevant=True,
        headline="Shurtan raises PP",
        countries=["Uzbekistan", "Kazakhstan"],
        language="en",
        analysis="What happened…",
        recommendation="Monitor PP prices.",
        i18n=NewsI18n(uz=NewsLocalized(headline="Shurtan PP narxini oshirdi")),
        confidence=0.9,
    )
    assert a.countries == ["Uzbekistan", "Kazakhstan"]
    assert a.language == "en"
    assert a.i18n is not None and a.i18n.uz is not None
    assert a.i18n.uz.headline == "Shurtan PP narxini oshirdi"


def test_irrelevant_clears_new_fields() -> None:
    from parsing.news_schemas import NewsArticle, NewsI18n, NewsLocalized

    a = NewsArticle(
        is_relevant=False,
        countries=["Russia"],
        language="ru",
        analysis="x",
        recommendation="y",
        i18n=NewsI18n(ru=NewsLocalized(headline="z")),
        confidence=0.8,
    )
    assert a.countries == []
    assert a.language is None
    assert a.analysis is None
    assert a.recommendation is None
    assert a.i18n is None


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
