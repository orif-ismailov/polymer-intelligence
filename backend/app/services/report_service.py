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
from app.core.time import to_display_tz, utcnow
from app.models.enums import ReportKind, ReportStatus
from app.models.reports import Report

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
        "news_uz": _snapshot_news(db, uz=True),
        "news_world": _snapshot_news(db, uz=False),
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


# ── Rendering ────────────────────────────────────────────────────────────────────

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

    # ── Биржа (UZEX, 24ч) ────────────────────────────────────────────────────
    tenders = snapshot.get("tenders_24h")
    if isinstance(tenders, dict) and int(tenders.get("count", 0) or 0) > 0:
        lines += ["", f"🏛 *Биржа и тендеры (24ч)* — новых позиций: {tenders['count']}"]
        for t in tenders.get("items") or []:  # type: ignore[union-attr]
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
        for r in reqs.get("items") or []:  # type: ignore[union-attr]
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

    # ── Новости ──────────────────────────────────────────────────────────────
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


_DIGEST_LANGS = ("ru", "en", "uz")


def _ai_digest(snapshot: dict[str, object]) -> dict[str, dict[str, str]] | None:
    """Best-effort multi-language digest: {"summary": {ru,en,uz}, "forecast": {ru,en,uz}}.

    The report_v2 prompt asks for strict JSON. Returns None on any failure — API error,
    non-JSON output, or a payload missing the Russian summary — so generate_report can
    degrade to the deterministic rule-based summary.
    """
    import json  # noqa: PLC0415

    prompt = _load_prompt(settings.REPORT_PROMPT_VERSION) or _load_prompt("v1")
    try:
        resp = _client.messages.create(
            model=settings.LLM_REPORT_MODEL,
            max_tokens=1024,
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

def generate_report(db: Session, *, use_llm: bool = True) -> Report:
    """Build today's digest and persist it as a draft. Does NOT commit.

    The AI part (summary + forecast in ru/en/uz) is best-effort: on any LLM failure the
    report degrades to the deterministic rule-based Russian summary with no forecast.
    Localized texts are journaled in data_snapshot["i18n"] for the API/webapp.
    """
    snapshot = build_snapshot(db)
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
    report = Report(
        kind=ReportKind.morning,
        period_start=today,
        period_end=today,
        title=f"Обзор рынка — {today.isoformat()}",
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
    logger.info("report_service.generate", extra={"report_id": report.id, "llm": used_llm})
    return report


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
