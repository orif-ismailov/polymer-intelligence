"""
AI sourcing waterfall + market intelligence (Phase 4).

run_sourcing applies the fixed business-priority waterfall (spec §6) for a buyer
request — inventory (1) → partner suppliers (2) → marketplace offers (3) → import
estimate (4) — plus market context (UZ / China averages). The PRIORITY is enforced
deterministically in code; the "recommended" option is the highest-priority available
one. source_request journals the result to sourcing_runs and stamps requests.ai.

market_overview powers the dashboard intel board (per-product buyers/sellers, average
seller price, average buyer target, spread).

Service axiom: db.flush() only — the router owns the commit.
"""

from __future__ import annotations

import decimal
import logging

import sqlalchemy as sa
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.enums import SellerOfferStatus
from app.models.marketplace import SellerOffer
from app.models.requests import Request
from app.models.sourcing import InventoryItem, PartnerSupplier, SourcingRun
from app.schemas.sourcing import MarketIntelRow

logger = logging.getLogger(__name__)

# Rough import logistics markup (USD/MT) added to a foreign benchmark for the
# import option, with a typical lead time. Tunable; deliberately conservative.
_IMPORT_LOGISTICS_USD = 120.0
_IMPORT_LEAD_DAYS = 18


def _f(v: decimal.Decimal | float | int | None) -> float | None:
    return float(v) if v is not None else None


def _import_estimate(db: Session, product_id: int) -> dict[str, object] | None:
    """Build an import option from the latest foreign benchmark, if any exists."""
    row = (
        db.execute(
            sa.text(
                """
                SELECT avg(price_avg) AS avg_price
                FROM price_points
                WHERE product_id = :pid
                  AND market IN ('CN', 'IR')
                  AND observed_on >= (CURRENT_DATE - INTERVAL '30 days')
                """
            ),
            {"pid": product_id},
        )
        .mappings()
        .one()
    )
    base = row["avg_price"]
    if base is None:
        return None
    return {
        "source": "import",
        "priority": 4,
        "label": "Импорт от производителя",
        "price": round(float(base) + _IMPORT_LOGISTICS_USD, 2),
        "currency": "USD",
        "qty_available": None,
        "lead_time_days": _IMPORT_LEAD_DAYS,
        "note": "Оценка: зарубежный бенчмарк + логистика",
    }


def _market_context(db: Session, product_id: int) -> dict[str, object]:
    """Latest UZ and China average prices for the product (context for the manager)."""
    rows = (
        db.execute(
            sa.text(
                """
                SELECT market, price_avg
                FROM price_points pp
                WHERE product_id = :pid AND market IN ('UZ', 'CN')
                  AND observed_on = (
                    SELECT max(observed_on) FROM price_points
                    WHERE product_id = :pid AND market = pp.market
                  )
                """
            ),
            {"pid": product_id},
        )
        .mappings()
        .all()
    )
    by_market = {str(r["market"]): _f(r["price_avg"]) for r in rows}
    return {"uz_avg": by_market.get("UZ"), "cn_avg": by_market.get("CN")}


def run_sourcing(db: Session, request: Request) -> dict[str, object]:
    """Apply the priority waterfall for a request and return the ranked result dict."""
    pid = request.product_id
    options: list[dict[str, object]] = []

    if pid is not None:
        for inv in db.query(InventoryItem).filter(InventoryItem.product_id == pid).all():
            options.append(
                {
                    "source": "inventory",
                    "priority": 1,
                    "label": inv.grade_text or "Наш склад",
                    "price": _f(inv.cost_price),
                    "currency": inv.currency,
                    "qty_available": _f(inv.qty_on_hand),
                    "lead_time_days": 0,
                    "note": inv.warehouse_city,
                }
            )

        partners = (
            db.query(PartnerSupplier)
            .filter(or_(PartnerSupplier.product_id == pid, PartnerSupplier.product_id.is_(None)))
            .all()
        )
        for p in partners:
            options.append(
                {
                    "source": "partner",
                    "priority": 2,
                    "label": p.name,
                    "price": _f(p.indicative_price),
                    "currency": p.currency,
                    "qty_available": None,
                    "lead_time_days": p.lead_time_days,
                    "note": p.notes,
                }
            )

        offers = (
            db.query(SellerOffer)
            .filter(
                SellerOffer.product_id == pid,
                SellerOffer.status == SellerOfferStatus.approved,
            )
            .all()
        )
        for o in offers:
            options.append(
                {
                    "source": "marketplace",
                    "priority": 3,
                    "label": (o.seller.company_name if o.seller else None) or "Продавец",
                    "price": _f(o.price),
                    "currency": o.currency,
                    "qty_available": _f(o.qty_available),
                    "lead_time_days": None,
                    "note": o.warehouse_city,
                }
            )

        import_opt = _import_estimate(db, pid)
        if import_opt is not None:
            options.append(import_opt)

    market = _market_context(db, pid) if pid is not None else {"uz_avg": None, "cn_avg": None}

    # Recommended = highest-priority available option; tie-break on the lowest price.
    def _rank_key(o: dict[str, object]) -> tuple[int, float]:
        pri = o["priority"]
        price = o["price"]
        return (
            pri if isinstance(pri, int) else 99,
            float(price) if isinstance(price, (int, float)) else float("inf"),
        )

    recommended: dict[str, object] | None = sorted(options, key=_rank_key)[0] if options else None

    return {
        "request": {
            "product_id": pid,
            "product_text": request.product_text,
            "grade_text": request.grade_text,
            "volume": _f(request.volume),
            "volume_unit": request.volume_unit,
            "target_price": _f(request.target_price),
            "currency": request.currency,
        },
        "options": options,
        "recommended": recommended,
        "market": market,
    }


def source_request(db: Session, request: Request) -> SourcingRun:
    """Run the waterfall, journal a sourcing_run, and stamp requests.ai. No commit."""
    result = run_sourcing(db, request)
    run = SourcingRun(request_id=request.id, model=None, prompt_version=None, result=result)
    db.add(run)
    # Stamp into requests.ai under "sourcing" (preserve any existing ai keys).
    request.ai = {**(request.ai or {}), "sourcing": result}
    db.flush()
    logger.info("sourcing_service.source_request", extra={"request_id": request.id})
    return run


def latest_sourcing_run(db: Session, request_id: int) -> SourcingRun | None:
    return (
        db.query(SourcingRun)
        .filter(SourcingRun.request_id == request_id)
        .order_by(SourcingRun.created_at.desc())
        .first()
    )


def market_overview(db: Session) -> list[MarketIntelRow]:
    """Per-product market intelligence: buyers/sellers, avg prices, spread."""
    sellers = (
        db.execute(
            sa.text(
                """
                SELECT p.code AS code, count(*) AS n, avg(o.price) AS avg_price
                FROM seller_offers o
                JOIN products p ON p.id = o.product_id
                WHERE o.status = 'approved'
                GROUP BY p.code
                """
            )
        )
        .mappings()
        .all()
    )
    buyers = (
        db.execute(
            sa.text(
                """
                SELECT p.code AS code, count(*) AS n, avg(r.target_price) AS avg_target
                FROM requests r
                JOIN products p ON p.id = r.product_id
                WHERE r.created_at >= now() - INTERVAL '30 days'
                GROUP BY p.code
                """
            )
        )
        .mappings()
        .all()
    )

    sell_map = {str(s["code"]): s for s in sellers}
    buy_map = {str(b["code"]): b for b in buyers}

    rows: list[MarketIntelRow] = []
    for code in sorted(set(sell_map) | set(buy_map)):
        s = sell_map.get(code)
        b = buy_map.get(code)
        avg_seller = _f(s["avg_price"]) if s else None
        avg_buyer = _f(b["avg_target"]) if b else None
        spread = (
            round(avg_seller - avg_buyer, 2)
            if avg_seller is not None and avg_buyer is not None
            else None
        )
        rows.append(
            MarketIntelRow(
                code=code,
                buyers=int(b["n"]) if b else 0,
                sellers=int(s["n"]) if s else 0,
                avg_seller_price=avg_seller,
                avg_buyer_target=avg_buyer,
                spread=spread,
            )
        )
    return rows
