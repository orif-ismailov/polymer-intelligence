"""
Semantic cross-source news dedup (Phase 7f).

Multiple sources (RSS feeds, Telegram channels) routinely report the same event.
cluster_articles() groups news dicts that describe the same story so the live feed,
the Mini-App cards, and the daily digest present one canonical article per story
(with the other sources attached as "also reported by") instead of N near-duplicates.

Deterministic + LLM-free: headline token Jaccard, boosted by shared companies or
products. Greedy single-linkage against each cluster's representative. Callers pass
articles pre-sorted by importance→recency, so the representative is the canonical
(highest-signal) item and later members are the additional sources.
"""

from __future__ import annotations

import re

# Russian + English function words that carry no story signal (kept small on purpose —
# the Jaccard threshold does the heavy lifting; this just avoids trivial glue-word matches).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "are", "was", "has",
        "have", "will", "its", "after", "amid", "over", "into", "out", "new", "say",
        "says", "said",
        "и", "в", "на", "по", "с", "за", "от", "для", "что", "как", "это", "из",
        "о", "об", "у", "был", "была", "было", "млн", "млрд",
    }
)

_WORD_RE = re.compile(r"[0-9a-zA-Zа-яёА-ЯЁ]+")

# Headline Jaccard alone is enough to merge; a lower bar merges when the two also
# share a company or product (strong same-event evidence).
HEADLINE_MATCH = 0.6
ENTITY_BOOST_MATCH = 0.35


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        tok
        for tok in (m.group(0).lower() for m in _WORD_RE.finditer(text or ""))
        if len(tok) > 2 and tok not in _STOPWORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _norm_set(items: object) -> frozenset[str]:
    if not isinstance(items, list):
        return frozenset()
    return frozenset(str(x).strip().lower() for x in items if str(x).strip())


def _same_story(a: dict[str, object], b: dict[str, object]) -> bool:
    ta = _tokens(str(a.get("headline") or ""))
    tb = _tokens(str(b.get("headline") or ""))
    jaccard = _jaccard(ta, tb)
    if jaccard >= HEADLINE_MATCH:
        return True
    shared_co = _norm_set(a.get("companies")) & _norm_set(b.get("companies"))
    shared_pr = _norm_set(a.get("related_products")) & _norm_set(b.get("related_products"))
    return bool(shared_co or shared_pr) and jaccard >= ENTITY_BOOST_MATCH


def cluster_articles(articles: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    """Greedy single-linkage clusters of same-story news dicts.

    Input order is preserved and defines representatives — pass articles already
    sorted by importance→recency so cluster[0] is the canonical item. Returns a list
    of clusters (each a non-empty list of the original dicts), in representative order.
    Each dict is compared only to a cluster's representative (single-linkage), which
    is O(n·k) for k clusters and avoids transitive over-merging.
    """
    clusters: list[list[dict[str, object]]] = []
    for art in articles:
        for cluster in clusters:
            if _same_story(art, cluster[0]):
                cluster.append(art)
                break
        else:
            clusters.append([art])
    return clusters
