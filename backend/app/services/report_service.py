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
    }


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


def render_markdown(snapshot: dict[str, object], summary: str) -> str:
    """Deterministic branded Russian markdown body for the report."""
    products = snapshot.get("products") or []
    lines: list[str] = [
        "📊 *Ежедневный обзор рынка*",
        f"_{snapshot.get('date', '')}_",
        "",
        "🇺🇿 *Узбекистан*",
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
    lines += [
        "",
        f"Активность за 7 дней: запросы — {snapshot.get('buy_requests_7d', 0)}, "
        f"предложения — {snapshot.get('sell_offers_7d', 0)}",
        "",
        "🤖 *AI Summary*",
        summary,
    ]
    return "\n".join(lines)


def _ai_summary(snapshot: dict[str, object]) -> str | None:
    """Best-effort one-paragraph LLM summary. Returns None on any failure."""
    import json  # noqa: PLC0415

    prompt = _load_prompt(settings.LLM_PROMPT_VERSION) or _load_prompt("v1")
    try:
        resp = _client.messages.create(
            model=settings.LLM_REPORT_MODEL,
            max_tokens=256,
            system=prompt,
            messages=[{"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)}],
        )
        parts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
        text = " ".join(parts).strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("report_service.ai_summary_failed", exc_info=True)
        return None


# ── Generation ───────────────────────────────────────────────────────────────────

def generate_report(db: Session, *, use_llm: bool = True) -> Report:
    """Build today's report and persist it as a draft. Does NOT commit."""
    snapshot = build_snapshot(db)
    summary = (_ai_summary(snapshot) if use_llm else None) or _rule_based_summary(snapshot)
    used_llm = use_llm and summary != _rule_based_summary(snapshot)
    content_md = render_markdown(snapshot, summary)

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
            f"{settings.LLM_REPORT_MODEL} {settings.LLM_PROMPT_VERSION}"
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
