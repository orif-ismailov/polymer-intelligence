"""
Dashboard home overview service.

Builds the GET /dashboard/summary payload in one set of read-only queries:
  - five KPI counts (buyers/sellers/active requests/hot leads/alert rules),
  - top 5 recent buyer requests,
  - top 5 recent seller offers (signals kind='sell_offer'),
  - top 5 recent AI-classified signals.

Read-only: no session.commit() (service-never-commits axiom). All queries are
static parameterless text — no user input is interpolated.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.schemas.dashboard import (
    DashboardAiSignalItem,
    DashboardKpis,
    DashboardOfferItem,
    DashboardRequestItem,
    DashboardSummary,
)

_KPIS_SQL = sa.text(
    """
    SELECT
      (SELECT count(*) FROM clients)                                          AS total_buyers,
      (SELECT count(*) FROM counterparties WHERE role = 'seller')            AS total_sellers,
      (SELECT count(*) FROM requests
         WHERE status NOT IN ('closed', 'cancelled'))                        AS active_requests,
      (SELECT count(*) FROM signals
         WHERE ai->>'classification' = 'HOT')                                AS hot_leads,
      (SELECT count(*) FROM alert_rules WHERE is_enabled)                    AS alert_rules
    """
)

_TOP_REQUESTS_SQL = sa.text(
    """
    SELECT r.id, r.number, r.product_id, p.code AS product, r.grade_text,
           r.volume, r.target_price, r.currency,
           r.urgency::text AS urgency, r.status::text AS status, r.created_at
    FROM requests r
    LEFT JOIN products p ON p.id = r.product_id
    ORDER BY r.created_at DESC
    LIMIT 5
    """
)

_TOP_OFFERS_SQL = sa.text(
    """
    SELECT s.id, s.kind::text AS kind, s.product_id, p.code AS product, s.grade_text,
           s.volume, s.price, s.currency, s.region, s.event_at
    FROM signals s
    LEFT JOIN products p ON p.id = s.product_id
    WHERE s.kind = 'sell_offer'
    ORDER BY s.event_at DESC
    LIMIT 5
    """
)

_AI_SIGNALS_SQL = sa.text(
    """
    SELECT s.id, s.kind::text AS kind, s.product_id, p.code AS product, s.grade_text,
           s.ai->>'classification'                              AS classification,
           (s.ai->>'lead_score')::float                         AS lead_score,
           COALESCE((s.ai->>'needs_review')::boolean, false)    AS needs_review,
           s.event_at
    FROM signals s
    LEFT JOIN products p ON p.id = s.product_id
    WHERE s.ai->>'classification' IS NOT NULL
    ORDER BY s.event_at DESC
    LIMIT 5
    """
)


def get_dashboard_summary(db: Session) -> DashboardSummary:
    """Return the dashboard home overview payload (KPIs + three top panels)."""
    kpis_row = db.execute(_KPIS_SQL).mappings().one()
    top_requests = db.execute(_TOP_REQUESTS_SQL).mappings().all()
    top_offers = db.execute(_TOP_OFFERS_SQL).mappings().all()
    ai_signals = db.execute(_AI_SIGNALS_SQL).mappings().all()

    return DashboardSummary(
        kpis=DashboardKpis.model_validate(dict(kpis_row)),
        top_requests=[DashboardRequestItem.model_validate(dict(r)) for r in top_requests],
        top_offers=[DashboardOfferItem.model_validate(dict(r)) for r in top_offers],
        ai_signals=[DashboardAiSignalItem.model_validate(dict(r)) for r in ai_signals],
    )
