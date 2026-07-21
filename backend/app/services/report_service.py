"""
News-engine report service (Phase 3).

Builds a daily market report from the derived price layer (price_points, market='UZ')
and recent signal activity, renders a branded Russian markdown body, optionally adds
an LLM "AI Summary", and writes a `reports` row in `draft` (human-in-the-loop: staff
approve → publish; only published reports are public). Also the read/transition
helpers used by the webapp news + dashboard reports APIs.

Service axiom (DEC-dep-owns-commit): db.flush() only — the router/task owns the commit.

LLM is best-effort: the summary call is isolated and any failure (placeholder key,
network, budget) degrades to a deterministic rule-based summary. Tests pass
use_llm=False for a fully deterministic, network-free path.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path

import anthropic
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.languages import SUPPORTED_LANGUAGES
from app.core.time import to_display_tz, utcnow
from app.models.enums import ReportKind, ReportStatus
from app.models.reports import Report
from app.services.news_dedup import cluster_articles

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "parsing" / "prompts"

# Module-level Anthropic client (built once at import; constructing it performs no
# network I/O — only stores the key, so it is safe under CI/tests). _ai_summary
# catches call-time failures; tests pass use_llm=False for a network-free path.
_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


@functools.lru_cache(maxsize=4)
def _load_prompt(version: str) -> str:
    path = _PROMPTS_DIR / f"report_{version}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── Snapshot ────────────────────────────────────────────────────────────────────

def build_snapshot(db: Session) -> dict[str, object]:
    """Aggregate the current market picture (UZ prices + 7-day activity)."""
    # Latest two UZ price points per product (last 60 days) → price + day-over-day delta.
    rows = (
        db.execute(
            sa.text(
                """
                SELECT p.code AS code, pp.price_avg AS price, pp.currency AS currency,
                       pp.unit AS unit, pp.observed_on AS observed_on
                FROM price_points pp
                JOIN products p ON p.id = pp.product_id
                WHERE pp.market = 'UZ'
                  AND pp.observed_on >= (CURRENT_DATE - INTERVAL '60 days')
                ORDER BY pp.product_id, pp.observed_on DESC
                """
            )
        )
        .mappings()
        .all()
    )

    by_code: dict[str, list[sa.engine.RowMapping]] = {}
    for r in rows:
        by_code.setdefault(str(r["code"]), []).append(r)

    products: list[dict[str, object]] = []
    for code, series in by_code.items():
        latest = series[0]
        prev = series[1] if len(series) > 1 else None
        price = float(latest["price"])
        delta = price - float(prev["price"]) if prev is not None else 0.0
        products.append(
            {
                "code": code,
                "price": round(price, 2),
                "currency": str(latest["currency"]),
                "unit": str(latest["unit"]),
                "delta": round(delta, 2),
                "observed_on": latest["observed_on"].isoformat(),
            }
        )
    products.sort(key=lambda p: str(p["code"]))

    activity = (
        db.execute(
            sa.text(
                """
                SELECT kind::text AS kind, count(*) AS n
                FROM signals
                WHERE event_at >= now() - INTERVAL '7 days'
                  AND kind IN ('buy_request', 'sell_offer')
                GROUP BY kind
                """
            )
        )
        .mappings()
        .all()
    )
    activity_map = {str(a["kind"]): int(a["n"]) for a in activity}

    today = to_display_tz(utcnow(), settings.TZ_DISPLAY).date()
    return {
        "date": today.isoformat(),
        "products": products,
        "buy_requests_7d": activity_map.get("buy_request", 0),
        "sell_offers_7d": activity_map.get("sell_offer", 0),
        # Digest sections (last 24 hours) — each helper degrades to empty on no data.
        "tenders_24h": _snapshot_tenders(db),
        "new_requests_24h": _snapshot_new_requests(db),
        "new_offers_24h": _snapshot_new_offers(db),
        "top_news": _snapshot_top_news(db),
        "news_uz": _snapshot_news(db, uz=True),
        "news_world": _snapshot_news(db, uz=False),
        # The three mandated sections (Phase 8c): rich, ranked, deduped news cards.
        "sections": _snapshot_sections(db),
        # Local Uzbekistan market intelligence (Phase 8g): CBU FX + UZEX exchange activity.
        "local_market": _snapshot_local_market(db),
    }


def _snapshot_local_market(db: Session, *, days: int = 7) -> dict[str, object]:
    """Local Uzbekistan market block: CBU FX rates + UZEX exchange activity.

    FX comes from the fx_rates table (latest date); UZEX activity is aggregated from
    kind in (deal/price_quote/sell_offer) on uzex* sources over `days`. Degrades to
    empty structures on no data (fx_rates may be empty until the CBU fetch runs).
    """
    fx_rows = (
        db.execute(
            sa.text(
                """
                SELECT ccy, rate FROM fx_rates
                WHERE rate_date = (SELECT max(rate_date) FROM fx_rates)
                ORDER BY ccy
                """
            )
        )
        .mappings()
        .all()
    )
    fx = [{"ccy": str(r["ccy"]), "rate": float(r["rate"])} for r in fx_rows]

    activity = (
        db.execute(
            sa.text(
                """
                SELECT sig.kind::text AS kind, count(*) AS n
                FROM signals sig JOIN sources src ON src.id = sig.source_id
                WHERE src.adapter LIKE 'uzex%'
                  AND sig.event_at >= now() - make_interval(days => :days)
                GROUP BY 1
                """
            ),
            {"days": days},
        )
        .mappings()
        .all()
    )
    counts = {str(a["kind"]): int(a["n"]) for a in activity}

    top = (
        db.execute(
            sa.text(
                """
                SELECT COALESCE(NULLIF(TRIM(sig.grade_text), ''), '—') AS label, count(*) AS n
                FROM signals sig JOIN sources src ON src.id = sig.source_id
                WHERE src.adapter LIKE 'uzex%' AND sig.kind = 'deal'
                  AND sig.event_at >= now() - make_interval(days => :days)
                GROUP BY 1 ORDER BY 2 DESC LIMIT 5
                """
            ),
            {"days": days},
        )
        .mappings()
        .all()
    )
    top_products = [{"label": str(t["label"]), "count": int(t["n"])} for t in top]

    return {
        "fx": fx,
        "exchange": {
            "deals": counts.get("deal", 0),
            "quotes": counts.get("price_quote", 0),
            "offers": counts.get("sell_offer", 0),
            "top_products": top_products,
        },
        "window_days": days,
    }


def _snapshot_tenders(db: Session) -> dict[str, object]:
    """New exchange/tender activity in the last 24h.

    Covers UZEX exchange offers + deals (uzex_* adapters) and buy-side procurement
    tenders from xarid.uzex.uz (xarid_tenders adapter, kind=buy_request).
    """
    rows = (
        db.execute(
            sa.text(
                """
                SELECT p.code AS code, s.kind::text AS kind, s.volume AS volume,
                       s.volume_unit AS volume_unit, s.price AS price, s.currency AS currency
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                LEFT JOIN products p ON p.id = s.product_id
                WHERE s.event_at >= now() - INTERVAL '24 hours'
                  AND s.kind IN ('sell_offer', 'deal', 'buy_request')
                  AND (src.adapter LIKE 'uzex%' OR src.adapter LIKE 'xarid%')
                ORDER BY s.event_at DESC
                LIMIT 50
                """
            )
        )
        .mappings()
        .all()
    )
    items = [
        {
            "code": str(r["code"]) if r["code"] else None,
            "kind": str(r["kind"]),
            "volume": float(r["volume"]) if r["volume"] is not None else None,
            "volume_unit": str(r["volume_unit"]) if r["volume_unit"] else "MT",
            "price": float(r["price"]) if r["price"] is not None else None,
            "currency": str(r["currency"]) if r["currency"] else None,
        }
        for r in rows[:5]
    ]
    return {"count": len(rows), "items": items}


def _snapshot_new_requests(db: Session) -> dict[str, object]:
    """New buyer purchase requests created on the platform in the last 24h."""
    rows = (
        db.execute(
            sa.text(
                """
                SELECT COALESCE(p.code, r.product_text, '—') AS label,
                       r.volume AS volume, r.volume_unit AS volume_unit
                FROM requests r
                LEFT JOIN products p ON p.id = r.product_id
                WHERE r.created_at >= now() - INTERVAL '24 hours'
                ORDER BY r.created_at DESC
                LIMIT 50
                """
            )
        )
        .mappings()
        .all()
    )
    items = [
        {
            "label": str(r["label"]),
            "volume": float(r["volume"]) if r["volume"] is not None else None,
            "volume_unit": str(r["volume_unit"]) if r["volume_unit"] else "MT",
        }
        for r in rows[:5]
    ]
    return {"count": len(rows), "items": items}


def _snapshot_new_offers(db: Session) -> dict[str, object]:
    """New marketplace seller offers created in the last 24h (any moderation status)."""
    n = db.execute(
        sa.text(
            """
            SELECT count(*) FROM seller_offers
            WHERE created_at >= now() - INTERVAL '24 hours'
            """
        )
    ).scalar()
    return {"count": int(n or 0)}


def _snapshot_news(db: Session, *, uz: bool) -> list[dict[str, object]]:
    """Recent news signals (last 24h) with a text excerpt, split UZ vs world by source country."""
    country_clause = "src.country = 'UZ'" if uz else "(src.country IS NULL OR src.country != 'UZ')"
    rows = (
        db.execute(
            sa.text(
                f"""
                SELECT src.name AS source_name, src.country AS country,
                       left(ri.content, 300) AS excerpt
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                LEFT JOIN raw_items ri ON ri.id = s.raw_item_id
                WHERE s.event_at >= now() - INTERVAL '24 hours'
                  AND s.kind = 'news'
                  AND {country_clause}
                ORDER BY s.event_at DESC
                LIMIT 6
                """  # noqa: S608 — country_clause is a hardcoded literal, not user input
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "source": str(r["source_name"]),
            "country": str(r["country"]) if r["country"] else None,
            "excerpt": (str(r["excerpt"]).strip() if r["excerpt"] else ""),
        }
        for r in rows
    ]


# Importance rank + which categories roll up into each themed report section.
_IMPORTANCE_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}
_NEWS_THEMES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("shutdowns", "🛑 *Остановки и ремонты*", frozenset({"plant_shutdown", "maintenance"})),
    ("projects", "🏭 *Заводы, проекты, инвестиции*",
     frozenset({"factories", "new_projects", "investment", "production"})),
    ("energy", "⛽ *Нефть и газ*", frozenset({"oil", "natural_gas", "energy", "refineries"})),
    ("logistics", "🚚 *Логистика и торговля*",
     frozenset({"logistics", "ports", "railways", "customs", "import", "export", "trade"})),
)


def _snapshot_top_news(db: Session, limit: int = 10) -> dict[str, object]:
    """Ranked news (last 24h) from kind='news' signals, reading the ai.news block.

    Ranked by importance then recency. Output is JSON-safe (no datetimes) so it can go
    straight into the LLM snapshot. Themed buckets group the top items by category.
    """
    rows = (
        db.execute(
            sa.text(
                """
                SELECT s.event_at, s.ai, src.name AS source_name, src.country AS country
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                WHERE s.kind = 'news'
                  AND s.event_at >= now() - INTERVAL '24 hours'
                  AND s.ai -> 'news' IS NOT NULL
                ORDER BY s.event_at DESC
                LIMIT 200
                """
            )
        )
        .mappings()
        .all()
    )

    articles: list[dict[str, object]] = []
    for r in rows:
        ai = r["ai"] if isinstance(r["ai"], dict) else {}
        news = ai.get("news") if isinstance(ai.get("news"), dict) else None
        if not news or not news.get("headline"):
            continue
        articles.append(
            {
                "headline": str(news.get("headline")),
                "category": news.get("category"),
                "importance": news.get("importance"),
                "market_impact": news.get("market_impact"),
                "summary": news.get("summary"),
                "companies": news.get("companies") or [],
                "country": news.get("country") or r["country"],
                "source": str(r["source_name"]),
                "_rank": (_IMPORTANCE_RANK.get(str(news.get("importance")), 0), r["event_at"]),
            }
        )

    articles.sort(key=lambda a: a["_rank"], reverse=True)  # type: ignore[arg-type,return-value]
    for a in articles:
        a.pop("_rank", None)  # drop the non-JSON-safe sort key

    # Cross-source dedup (Phase 7f): collapse same-story items so the digest doesn't
    # repeat one event N times; the representative carries a merged source count.
    clusters = cluster_articles(articles)
    reps: list[dict[str, object]] = []
    for members in clusters:
        rep = members[0]
        rep["merged_count"] = len(members)
        reps.append(rep)
    top = reps[:limit]

    themes: dict[str, list[str]] = {}
    for a in top:
        cat = str(a.get("category") or "")
        for key, _label, cats in _NEWS_THEMES:
            if cat in cats:
                themes.setdefault(key, []).append(str(a["headline"]))
    return {"count": len(reps), "top": top, "themes": themes}


# The three mandated report sections (Phase 8c). Each is a scope over the last 24h of
# classified news, ranked + cross-source-deduped + localized to ru, capped at 10 items.
_REPORT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("uzbekistan", "uzbekistan"),
    ("global", "global"),
    ("producers", "producers"),
)
_SECTION_ITEM_CAP = 10


def _snapshot_sections(db: Session) -> dict[str, object]:
    """Build the 🇺🇿 Uzbekistan / 🌍 Global / 🏭 Producer sections (≤10 cards each)."""
    from app.services import news_service  # noqa: PLC0415 — avoid import cycle at module load

    out: dict[str, object] = {}
    for key, scope in _REPORT_SECTIONS:
        cards = news_service.list_news_articles(
            db, days=1, scope=scope, limit=_SECTION_ITEM_CAP, lang="ru"
        )
        for card in cards:
            card.pop("i18n", None)  # raw ru/uz/en variants aren't needed in the stored snapshot
        out[key] = cards
    return out


# ── Rendering ────────────────────────────────────────────────────────────────────

def _merged_suffix(article: object) -> str:
    """" (+N)" when a story was reported by more than one source (Phase 7f), else ""."""
    if isinstance(article, dict):
        count = article.get("merged_count")
        if isinstance(count, int) and count > 1:
            return f" (+{count - 1})"
    return ""


_SECTION_HEADERS: tuple[tuple[str, str], ...] = (
    ("uzbekistan", "🇺🇿 *Рынок Узбекистана*"),
    ("global", "🌍 *Мировой рынок*"),
    ("producers", "🏭 *Новости производителей*"),
)
_IMP_DOT = {"high": "🔴", "medium": "🟡", "low": "⚪"}
_IMPACT_ARROW = {"positive": "📈", "negative": "📉", "neutral": "➖"}


def _render_sections(sections: dict[str, object]) -> list[str]:
    """Render the three mandated report sections as markdown card blocks."""
    lines: list[str] = []
    for key, header in _SECTION_HEADERS:
        items = sections.get(key)
        if not isinstance(items, list) or not items:
            continue
        lines += ["", header]
        for n in items[:_SECTION_ITEM_CAP]:
            if not isinstance(n, dict):
                continue
            mark = _IMP_DOT.get(str(n.get("importance")), "⚪") + _IMPACT_ARROW.get(
                str(n.get("market_impact")), ""
            )
            head = str(n.get("headline") or "").strip()
            src = n.get("source_name") or "—"
            lines.append(f"{mark} *{head}* — _{src}_{_merged_suffix(n)}")
            summ = str(n.get("summary") or "").strip().replace("\n", " ")
            if summ:
                lines.append(summ if len(summ) <= 200 else summ[:197] + "…")
            rec = str(n.get("recommendation") or "").strip()
            if rec:
                lines.append(f"💡 {rec}")
            prods = n.get("related_products")
            if isinstance(prods, list) and prods:
                lines.append("📦 " + ", ".join(str(p) for p in prods[:6]))
    return lines


_FX_DISPLAY_CCY: tuple[str, ...] = ("USD", "EUR", "RUB", "CNY", "KZT")


def _as_int(value: object) -> int:
    """Best-effort int from a JSONB-sourced object value (0 on anything unparseable)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return 0


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _fx_rate_map(fx: object) -> dict[str, float]:
    """Build {ccy: rate} from the snapshot's fx list."""
    out: dict[str, float] = {}
    if isinstance(fx, list):
        for r in fx:
            if isinstance(r, dict):
                rate = _as_float(r.get("rate"))
                if rate is not None:
                    out[str(r.get("ccy"))] = rate
    return out


def _render_local_market(lm: dict[str, object]) -> list[str]:
    """Render the local Uzbekistan market block (CBU FX + UZEX activity). [] when empty."""
    ex_raw = lm.get("exchange")
    ex = ex_raw if isinstance(ex_raw, dict) else {}
    deals = _as_int(ex.get("deals"))
    quotes = _as_int(ex.get("quotes"))
    offers = _as_int(ex.get("offers"))
    rates = _fx_rate_map(lm.get("fx"))
    if not rates and not (deals or quotes or offers):
        return []
    lines: list[str] = ["", "🇺🇿 *Локальный рынок (UZEX / ЦБ РУз)*"]
    bits = [f"{c} {rates[c]:,.0f}" for c in _FX_DISPLAY_CCY if c in rates]
    if bits:
        lines.append("💱 Курс ЦБ (сум за 1): " + " · ".join(bits))
    if deals or quotes or offers:
        days = _as_int(lm.get("window_days")) or 7
        lines.append(
            f"🏛 Биржа UZEX ({days} дн.): сделок — {deals}, "
            f"котировок — {quotes}, предложений — {offers}"
        )
        top = ex.get("top_products")
        if isinstance(top, list):
            for tp in top:
                if isinstance(tp, dict):
                    lines.append(f"• {tp.get('label', '—')} — {_as_int(tp.get('count'))}")
    return lines


def _rule_based_summary(snapshot: dict[str, object]) -> str:
    products = snapshot.get("products") or []
    if not isinstance(products, list) or not products:
        return "Недостаточно данных для анализа за сегодня."
    ups = sum(1 for p in products if float(p["delta"]) > 0)
    downs = sum(1 for p in products if float(p["delta"]) < 0)
    if ups > downs:
        return "Цены по большинству позиций выросли за период."
    if downs > ups:
        return "Цены по большинству позиций снизились за период."
    return "Цены в целом стабильны за период."


def render_markdown(
    snapshot: dict[str, object], summary: str, forecast: str | None = None
) -> str:
    """Deterministic branded Russian markdown body for the daily digest.

    Renders every section for which the snapshot carries data and silently skips the
    rest — old (pre-digest) snapshots without the 24h keys render exactly as before.
    """
    products = snapshot.get("products") or []
    lines: list[str] = [
        "📊 *Ежедневный обзор рынка*",
        f"_{snapshot.get('date', '')}_",
        "",
        "🇺🇿 *Цены — Узбекистан*",
    ]
    if isinstance(products, list) and products:
        for p in products:
            delta = float(p["delta"])
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"• {p['code']}: {float(p['price']):,.0f} {p['currency']}/{p['unit']} "
                f"({sign}{delta:.0f})"
            )
    else:
        lines.append("• нет данных")

    # ── Локальный рынок: CBU FX + UZEX activity (Phase 8g) ────────────────────
    local_market = snapshot.get("local_market")
    if isinstance(local_market, dict):
        lines += _render_local_market(local_market)

    # ── Биржа (UZEX, 24ч) ────────────────────────────────────────────────────
    tenders = snapshot.get("tenders_24h")
    if isinstance(tenders, dict) and int(tenders.get("count", 0) or 0) > 0:
        lines += ["", f"🏛 *Биржа и тендеры (24ч)* — новых позиций: {tenders['count']}"]
        for t in tenders.get("items") or []:
            bits = [str(t.get("code") or "—")]
            if t.get("volume") is not None:
                bits.append(f"{float(t['volume']):,.0f} {t.get('volume_unit', 'MT')}")
            if t.get("price") is not None:
                bits.append(f"{float(t['price']):,.0f} {t.get('currency') or ''}".strip())
            lines.append("• " + " · ".join(bits))

    # ── Новые заявки покупателей (24ч) ───────────────────────────────────────
    reqs = snapshot.get("new_requests_24h")
    if isinstance(reqs, dict) and int(reqs.get("count", 0) or 0) > 0:
        lines += ["", f"🛒 *Новые заявки покупателей (24ч)*: {reqs['count']}"]
        for r in reqs.get("items") or []:
            vol = (
                f" — {float(r['volume']):,.0f} {r.get('volume_unit', 'MT')}"
                if r.get("volume") is not None
                else ""
            )
            lines.append(f"• {r.get('label', '—')}{vol}")

    # ── Новые предложения продавцов (24ч) ────────────────────────────────────
    offers = snapshot.get("new_offers_24h")
    if isinstance(offers, dict) and int(offers.get("count", 0) or 0) > 0:
        lines += ["", f"📦 *Новые предложения на маркете (24ч)*: {offers['count']}"]

    # ── Three mandated sections (Phase 8c): 🇺🇿 UZ / 🌍 Global / 🏭 Producers ──
    sections = snapshot.get("sections")
    has_sections = isinstance(sections, dict) and any(
        isinstance(v, list) and v for v in sections.values()
    )
    if has_sections:
        lines += _render_sections(sections)  # type: ignore[arg-type]
    else:
        # Legacy path (pre-8c snapshots / tests): ranked top-news + excerpt fallback.
        top_news = snapshot.get("top_news")
        if isinstance(top_news, dict) and (top_news.get("top") or []):
            top = list(top_news.get("top") or [])
            lines += ["", f"📰 *Топ новостей (24ч)* — всего: {top_news.get('count', len(top))}"]
            for n in top[:8]:
                if not isinstance(n, dict):
                    continue
                mark = _IMP_DOT.get(str(n.get("importance")), "⚪") + _IMPACT_ARROW.get(
                    str(n.get("market_impact")), ""
                )
                lines.append(
                    f"{mark} {str(n.get('headline') or '').strip()} — "
                    f"_{n.get('source', '—')}_{_merged_suffix(n)}"
                )
            themes = top_news.get("themes") if isinstance(top_news.get("themes"), dict) else {}
            for key, label, _cats in _NEWS_THEMES:
                heads = themes.get(key) if isinstance(themes, dict) else None
                if isinstance(heads, list) and heads:
                    lines += ["", label]
                    lines += [f"• {h}" for h in heads[:4]]

        def _news_block(title: str, items: object) -> None:
            if isinstance(items, list) and items:
                lines.append("")
                lines.append(title)
                for n in items[:4]:
                    excerpt = str(n.get("excerpt") or "").strip().replace("\n", " ")
                    if len(excerpt) > 160:
                        excerpt = excerpt[:157] + "…"
                    if excerpt:
                        lines.append(f"• [{n.get('source', '—')}] {excerpt}")

        _news_block("🇺🇿 *Новости Узбекистана*", snapshot.get("news_uz"))
        _news_block("🌍 *Мировая нефтехимия*", snapshot.get("news_world"))

    lines += [
        "",
        f"Активность за 7 дней: запросы — {snapshot.get('buy_requests_7d', 0)}, "
        f"предложения — {snapshot.get('sell_offers_7d', 0)}",
        "",
        "🤖 *AI Summary*",
        summary,
    ]
    if forecast:
        lines += ["", "🔮 *Прогноз*", forecast]
    return "\n".join(lines)


# ── Telegram channel digest (Phase 7e) ─────────────────────────────────────────────
# The full render_markdown() body is the archival report shown in the dashboard/webapp.
# The Telegram channel wants a compact, news-forward push that fits comfortably in one
# message and carries the brand footer. Telegram hard-limits a text message at 4096
# chars; we self-impose 1500 so the digest stays skimmable on a phone.

TELEGRAM_DIGEST_LIMIT = 1500
_POWERED_BY = "🤖 Powered by IMEX AI"
_TG_IMPORTANCE = {"high": "🔴", "medium": "🟡", "low": "⚪"}
_TG_IMPACT = {"positive": "📈", "negative": "📉", "neutral": "➖"}


def _digest_summary_ru(snapshot: dict[str, object]) -> str:
    """The Russian AI summary if the report carried one, else the rule-based line."""
    i18n = snapshot.get("i18n")
    if isinstance(i18n, dict):
        summary = i18n.get("summary")
        if isinstance(summary, dict):
            ru = str(summary.get("ru") or "").strip()
            if ru:
                return ru
    return _rule_based_summary(snapshot)


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_telegram_digest(
    snapshot: dict[str, object], *, limit: int = TELEGRAM_DIGEST_LIMIT
) -> str:
    """Compact, news-forward Telegram push (≤ `limit` chars, brand footer).

    Priority order under the char budget: title → AI summary → ranked top news →
    themed one-liners → a UZ-price movers line. Lower-priority sections are dropped
    (not truncated mid-item) when the budget is tight; the whole body is hard-capped
    as a final guard. The "Powered by IMEX AI" footer is always present.
    """
    footer = f"\n\n—\n{_POWERED_BY}"
    budget = limit - len(footer)

    def _fits(candidate: list[str]) -> bool:
        return len("\n".join(candidate)) <= budget

    lines: list[str] = [f"📰 *Обзор рынка — {snapshot.get('date', '')}*"]

    summary = _digest_summary_ru(snapshot)
    if summary:
        block = [*lines, "", _truncate(summary, 350)]
        if _fits(block):
            lines = block

    # Three mandated sections (Phase 8c) — compact: header + top headlines each.
    sections = snapshot.get("sections")
    has_sections = isinstance(sections, dict) and any(
        isinstance(v, list) and v for v in sections.values()
    )
    if has_sections:
        for key, sec_header in _SECTION_HEADERS:
            items = sections.get(key) if isinstance(sections, dict) else None
            if not isinstance(items, list) or not items:
                continue
            block_header = [*lines, "", sec_header]
            if not _fits(block_header):
                break
            lines = block_header
            for n in items[:5]:
                if not isinstance(n, dict):
                    continue
                mark = _TG_IMPORTANCE.get(str(n.get("importance")), "⚪") + _TG_IMPACT.get(
                    str(n.get("market_impact")), ""
                )
                head = str(n.get("headline") or "").strip()
                if not head:
                    continue
                src = n.get("source_name") or n.get("source") or "—"
                candidate = [*lines, f"{mark} {head} — _{src}_{_merged_suffix(n)}"]
                if not _fits(candidate):
                    break
                lines = candidate
    else:
        # Legacy path (pre-8c snapshots): ranked top news + themed one-liners.
        top_news = snapshot.get("top_news")
        top = list(top_news.get("top") or []) if isinstance(top_news, dict) else []
        if top:
            header = [*lines, "", "*Главные новости:*"]
            if _fits(header):
                lines = header
                for n in top:
                    if not isinstance(n, dict):
                        continue
                    mark = _TG_IMPORTANCE.get(str(n.get("importance")), "⚪") + _TG_IMPACT.get(
                        str(n.get("market_impact")), ""
                    )
                    head = str(n.get("headline") or "").strip()
                    if not head:
                        continue
                    candidate = [*lines, f"{mark} {head} — _{n.get('source', '—')}_{_merged_suffix(n)}"]
                    if not _fits(candidate):
                        break
                    lines = candidate

        themes = top_news.get("themes") if isinstance(top_news, dict) else None
        if isinstance(themes, dict):
            for key, label, _cats in _NEWS_THEMES:
                heads = themes.get(key)
                if isinstance(heads, list) and heads:
                    candidate = [*lines, f"{label}: " + "; ".join(str(h) for h in heads[:2])]
                    if not _fits(candidate):
                        break
                    lines = candidate

    # UZ price movers — one line, biggest absolute moves first.
    products = snapshot.get("products")
    if isinstance(products, list) and products:
        movers = sorted(products, key=lambda p: abs(float(p.get("delta", 0) or 0)), reverse=True)
        bits = []
        for p in movers[:3]:
            delta = float(p.get("delta", 0) or 0)
            sign = "+" if delta >= 0 else ""
            bits.append(f"{p.get('code')} {float(p['price']):,.0f}{p.get('currency', '')} ({sign}{delta:.0f})")
        candidate = [*lines, "", "💱 " + " · ".join(bits)]
        if _fits(candidate):
            lines = candidate

    # CBU FX rates — one compact line (Phase 8g local-market enrichment).
    lm = snapshot.get("local_market")
    rates = _fx_rate_map(lm.get("fx")) if isinstance(lm, dict) else {}
    if rates:
        fx_bits = [f"{c} {rates[c]:,.0f}" for c in _FX_DISPLAY_CCY if c in rates]
        if fx_bits:
            candidate = [*lines, "🇺🇿 ЦБ: " + " · ".join(fx_bits[:4])]
            if _fits(candidate):
                lines = candidate

    body = "\n".join(lines)
    if len(body) > budget:  # final hard guard (should not trigger given the checks above)
        body = body[: budget - 1].rstrip() + "…"
    return body + footer


# One source of truth: the digest speaks every language the platform supports
# (app/core/languages.py) — currently ru/en/tr/uz/fa/zh. Adding a platform language
# extends the digest automatically (the report prompt lists them explicitly;
# keep it in sync when SUPPORTED_LANGUAGES grows).
_DIGEST_LANGS = SUPPORTED_LANGUAGES


def _ai_digest(snapshot: dict[str, object]) -> dict[str, dict[str, str]] | None:
    """Best-effort multi-language digest: summary + forecast in every supported language.

    The report prompt asks for strict JSON. Returns None on any failure — API error,
    non-JSON output, or a payload missing the Russian summary — so generate_report can
    degrade to the deterministic rule-based summary.
    """
    import json  # noqa: PLC0415

    prompt = _load_prompt(settings.REPORT_PROMPT_VERSION) or _load_prompt("v1")
    try:
        resp = _client.messages.create(
            model=settings.LLM_REPORT_MODEL,
            max_tokens=2048,
            system=prompt,
            messages=[{"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)}],
        )
        parts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
        text = " ".join(parts).strip()
        if not text:
            return None
        # Tolerate accidental markdown fences around the JSON.
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        data = json.loads(text)
        summary = data.get("summary") or {}
        forecast = data.get("forecast") or {}
        if not isinstance(summary, dict) or not str(summary.get("ru", "")).strip():
            return None
        return {
            "summary": {k: str(summary.get(k, "")).strip() for k in _DIGEST_LANGS},
            "forecast": {k: str(forecast.get(k, "")).strip() for k in _DIGEST_LANGS}
            if isinstance(forecast, dict)
            else dict.fromkeys(_DIGEST_LANGS, ""),
        }
    except Exception:  # noqa: BLE001
        logger.warning("report_service.ai_digest_failed", exc_info=True)
        return None


# ── Generation ───────────────────────────────────────────────────────────────────

# Morning vs evening brief (Phase 8c). Same builder, different schedule + label.
_SESSION_META: dict[str, tuple[ReportKind, str]] = {
    "morning": (ReportKind.morning, "Утренний обзор рынка"),
    "evening": (ReportKind.evening, "Вечерний обзор рынка"),
}


def _session_meta(session: str, date_iso: str) -> tuple[ReportKind, str]:
    """Map a session label to its (ReportKind, title). Unknown → morning."""
    kind, prefix = _SESSION_META.get(session, _SESSION_META["morning"])
    return kind, f"{prefix} — {date_iso}"


def generate_report(db: Session, *, use_llm: bool = True, session: str = "morning") -> Report:
    """Build a market digest (morning or evening) and persist it as a draft. No commit.

    The AI part (summary + forecast in ru/en/uz) is best-effort: on any LLM failure the
    report degrades to the deterministic rule-based Russian summary with no forecast.
    Localized texts are journaled in data_snapshot["i18n"] for the API/webapp.
    """
    snapshot = build_snapshot(db)
    snapshot["session"] = session
    digest = _ai_digest(snapshot) if use_llm else None
    used_llm = digest is not None

    if digest is not None:
        summary = digest["summary"]["ru"]
        forecast: str | None = digest["forecast"].get("ru") or None
        snapshot["i18n"] = digest
    else:
        summary = _rule_based_summary(snapshot)
        forecast = None

    content_md = render_markdown(snapshot, summary, forecast)

    today = to_display_tz(utcnow(), settings.TZ_DISPLAY).date()
    kind, title = _session_meta(session, today.isoformat())
    report = Report(
        kind=kind,
        period_start=today,
        period_end=today,
        title=title,
        content_md=content_md,
        data_snapshot=snapshot,
        status=ReportStatus.draft,
        generated_by=(
            f"{settings.LLM_REPORT_MODEL} {settings.REPORT_PROMPT_VERSION}"
            if used_llm
            else "rule_based"
        ),
    )
    db.add(report)
    db.flush()
    logger.info(
        "report_service.generate",
        extra={"report_id": report.id, "llm": used_llm, "session": session},
    )
    return report


# ── Breaking news (Phase 8c) ────────────────────────────────────────────────────────
# High-importance news is pushed to the channel immediately instead of waiting for the
# next scheduled brief. Each pushed story is marked (signals.extra.breaking_pushed) so a
# beat task can poll without re-sending. Same-story items merge into one alert.

_BREAKING_HEADER = "🚨 *СРОЧНО — важная новость*"


def pending_breaking_news(
    db: Session, *, minutes: int = 120, limit: int = 20
) -> list[dict[str, object]]:
    """Recent high-importance news not yet pushed, merged per story.

    Returns a list of {"card": <ru-localized card>, "ids": [signal ids in the cluster]}.
    Marking every id in the cluster prevents re-pushing the same event from a second source.
    """
    from app.services import news_service  # noqa: PLC0415 — avoid import cycle at module load

    rows = (
        db.execute(
            sa.text(
                """
                SELECT s.id AS id, s.event_at AS event_at, s.ai AS ai,
                       src.name AS source_name, src.country AS country
                FROM signals s
                JOIN sources src ON src.id = s.source_id
                WHERE s.kind = 'news'
                  AND s.ai -> 'news' ->> 'importance' = 'high'
                  AND COALESCE(s.ai->'news'->>'approval', 'approved') NOT IN ('pending', 'rejected')
                  AND s.event_at >= now() - make_interval(mins => :minutes)
                  AND COALESCE((s.extra ->> 'breaking_pushed')::boolean, false) = false
                ORDER BY s.event_at DESC
                LIMIT :limit
                """
            ),
            {"minutes": minutes, "limit": limit},
        )
        .mappings()
        .all()
    )
    cards = [news_service._article_card(r) for r in rows if isinstance(r["ai"], dict)]
    out: list[dict[str, object]] = []
    for members in cluster_articles(cards):
        rep = news_service._localize(dict(members[0]), "ru")
        rep.pop("i18n", None)
        out.append({"card": rep, "ids": [int(str(m["id"])) for m in members]})
    return out


def mark_breaking_pushed(db: Session, ids: list[int]) -> None:
    """Flag signals as already pushed as breaking news (idempotent)."""
    if not ids:
        return
    db.execute(
        sa.text(
            "UPDATE signals "
            "SET extra = COALESCE(extra, '{}'::jsonb) "
            "         || jsonb_build_object('breaking_pushed', true, 'breaking_pushed_at', CAST(:ts AS text)) "
            "WHERE id = ANY(CAST(:ids AS bigint[]))"
        ),
        {"ts": utcnow().isoformat(), "ids": ids},
    )


def render_breaking_alert(card: dict[str, object]) -> str:
    """Compact single-story breaking-news push for the Telegram channel."""
    head = str(card.get("headline") or "").strip()
    mark = "🔴" + _IMPACT_ARROW.get(str(card.get("market_impact")), "")
    lines = [_BREAKING_HEADER, "", f"{mark} *{head}*"]
    summary = str(card.get("summary") or "").strip()
    if summary:
        lines += ["", _truncate(summary, 400)]
    rec = str(card.get("recommendation") or "").strip()
    if rec:
        lines += ["", f"💡 {rec}"]
    src = card.get("source_name")
    if src:
        lines += ["", f"_{src}_{_merged_suffix(card)}"]
    return "\n".join(lines) + f"\n\n—\n{_POWERED_BY}"


# ── Reads ────────────────────────────────────────────────────────────────────────

def list_published(db: Session, limit: int = 30) -> list[Report]:
    return (
        db.query(Report)
        .filter(Report.status == ReportStatus.published)
        .order_by(Report.published_at.desc().nullslast(), Report.created_at.desc())
        .limit(limit)
        .all()
    )


def get_published(db: Session, report_id: int) -> Report | None:
    return (
        db.query(Report)
        .filter(Report.id == report_id, Report.status == ReportStatus.published)
        .first()
    )


def list_for_review(db: Session, limit: int = 50) -> list[Report]:
    """All non-rejected reports for the dashboard (newest first)."""
    return (
        db.query(Report)
        .filter(Report.status != ReportStatus.rejected)
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )


def get_report(db: Session, report_id: int) -> Report | None:
    return db.query(Report).filter(Report.id == report_id).first()


# ── Transitions (dashboard) ──────────────────────────────────────────────────────

def approve_report(db: Session, report: Report, staff_user_id: int) -> Report:
    report.status = ReportStatus.approved
    report.approved_by = staff_user_id
    db.flush()
    return report


def publish_report(db: Session, report: Report) -> Report:
    """Mark a report published (set published_at). Channel delivery is a separate task."""
    report.status = ReportStatus.published
    if report.published_at is None:
        report.published_at = utcnow()
    db.flush()
    return report


def reject_report(db: Session, report: Report) -> Report:
    report.status = ReportStatus.rejected
    db.flush()
    return report


# ── Admin news-ops stats (Phase 8d) ─────────────────────────────────────────────────

def news_admin_stats(db: Session, *, ai_enabled: bool) -> dict[str, object]:
    """One-row snapshot for the dashboard admin panel: sources, scans, pending AI, and
    AI health (recent extractor errors + daily budget usage) so a failing API surfaces
    instead of showing silent zeros."""
    row = (
        db.execute(
            sa.text(
                """
                SELECT
                  (SELECT count(*) FROM sources) AS total_sources,
                  (SELECT count(*) FROM sources WHERE is_enabled) AS active_sources,
                  (SELECT count(*) FROM sources WHERE consecutive_failures > 0) AS failed_sources,
                  (SELECT max(last_fetch_at) FROM sources) AS last_scan,
                  (SELECT max(published_at) FROM reports WHERE status = 'published')
                    AS last_published_report,
                  (SELECT count(*) FROM raw_items ri JOIN sources s2 ON s2.id = ri.source_id
                     WHERE s2.config ->> 'content_kind' = 'news'
                       AND ri.parse_status IN ('pending', 'budget_deferred')) AS pending_ai_analysis,
                  (SELECT count(*) FROM signals
                     WHERE kind = 'news' AND event_at >= date_trunc('day', now())) AS today_published_news,
                  (SELECT count(*) FROM parse_runs
                     WHERE status = 'error' AND parser LIKE '%extract%'
                       AND created_at >= now() - INTERVAL '30 minutes') AS ai_errors_recent,
                  (SELECT left(error, 300) FROM parse_runs
                     WHERE status = 'error' AND parser LIKE '%extract%'
                       AND created_at >= now() - INTERVAL '30 minutes'
                     ORDER BY created_at DESC LIMIT 1) AS ai_last_error
                """
            )
        )
        .mappings()
        .one()
    )

    budget_pct = 0.0
    try:  # budget display must never 500 the panel (Redis optional)
        from parsing.budget import DAILY_TOKEN_LIMIT, daily_spend  # noqa: PLC0415

        if DAILY_TOKEN_LIMIT:
            budget_pct = round(daily_spend() / DAILY_TOKEN_LIMIT * 100, 1)
    except Exception:  # noqa: BLE001
        budget_pct = 0.0

    # "error" = failing RIGHT NOW (recent window), not "failed at some point today".
    # An old outage's errors age out of the window once the extractor recovers.
    ai_errors = int(row["ai_errors_recent"] or 0)
    if not ai_enabled:
        ai_status = "off"
    elif ai_errors > 0:
        ai_status = "error"
    else:
        ai_status = "on"

    return {
        "total_sources": int(row["total_sources"] or 0),
        "active_sources": int(row["active_sources"] or 0),
        "failed_sources": int(row["failed_sources"] or 0),
        "last_scan": row["last_scan"],
        "last_published_report": row["last_published_report"],
        "pending_ai_analysis": int(row["pending_ai_analysis"] or 0),
        "today_published_news": int(row["today_published_news"] or 0),
        "ai_enabled": ai_enabled,
        "ai_status": ai_status,
        "ai_errors_recent": ai_errors,
        "ai_last_error": row["ai_last_error"],
        "budget_used_pct": budget_pct,
    }
