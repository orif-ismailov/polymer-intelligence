"""
Tests for Phase 7f — semantic cross-source news dedup (app.services.news_dedup).

cluster_articles groups same-story news dicts (headline Jaccard, boosted by shared
companies/products) so the feed, cards, and digest show one canonical article per
story. Pure function — no DB.
"""

from __future__ import annotations


def _art(headline: str, *, importance: str = "medium", companies=None, products=None) -> dict:
    return {
        "headline": headline,
        "importance": importance,
        "companies": companies or [],
        "related_products": products or [],
    }


def test_identical_headlines_different_sources_merge() -> None:
    from app.services.news_dedup import cluster_articles

    arts = [
        _art("Brent crude climbs on OPEC output cuts"),
        _art("Brent crude climbs after OPEC output cuts"),  # "after"/"on" are stopwords
    ]
    clusters = cluster_articles(arts)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_entity_boost_merges_partial_overlap() -> None:
    from app.services.news_dedup import cluster_articles

    arts = [
        _art("Shurtan GCC halts line", companies=["Shurtan"], products=["PP"]),
        _art("Shurtan halts output", companies=["Shurtan"], products=["PP"]),
    ]
    clusters = cluster_articles(arts)
    assert len(clusters) == 1, "shared company + partial headline overlap should merge"


def test_distinct_stories_stay_separate() -> None:
    from app.services.news_dedup import cluster_articles

    arts = [
        _art("Brent crude rises on supply worries"),
        _art("Uzbekistan opens new PVC plant in Navoi", products=["PVC"]),
    ]
    clusters = cluster_articles(arts)
    assert len(clusters) == 2


def test_no_entity_overlap_does_not_merge_on_weak_headline() -> None:
    from app.services.news_dedup import cluster_articles

    # Some shared generic words but no shared company/product and low Jaccard → separate.
    arts = [
        _art("Government approves petrochemical investment package"),
        _art("Government approves railway modernization budget"),
    ]
    clusters = cluster_articles(arts)
    assert len(clusters) == 2


def test_representative_is_first_seen() -> None:
    from app.services.news_dedup import cluster_articles

    arts = [
        _art("Shurtan halts PP line for maintenance", importance="high", companies=["Shurtan"], products=["PP"]),
        _art("Shurtan halts PP output", importance="low", companies=["Shurtan"], products=["PP"]),
    ]
    clusters = cluster_articles(arts)
    assert len(clusters) == 1
    assert clusters[0][0]["importance"] == "high"  # input order defines the representative


def test_empty_input() -> None:
    from app.services.news_dedup import cluster_articles

    assert cluster_articles([]) == []
