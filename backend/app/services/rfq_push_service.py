"""RFQ supplier-push bookkeeping (R4 / P4 — T3.3 + T3.4).

Two jobs, both small: record that a supplier was told about an RFQ (exactly
once), and read that record back for staff.

The "exactly once" is the schema's, not this module's: the insert is
`ON CONFLICT DO NOTHING` on `uq_rfq_push_target`, so a retry after a crash
mid-run notifies nobody twice — no bookkeeping in the task needed.
"""

from __future__ import annotations

import datetime
import decimal
import logging
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.marketplace.models import RfqPushLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PushedSupplier:
    """One row of the "who did we tell?" panel."""

    company_id: int
    company_name: str | None
    score: decimal.Decimal
    rank: int
    notified_at: datetime.datetime


def record_push(
    db: Session, request_id: int, company_id: int, *, score: decimal.Decimal, rank: int
) -> bool:
    """Claim the right to notify this company about this RFQ.

    Returns True when the claim was new (so the caller should send the bell) and
    False when this supplier had already been told. Flush-only — the caller owns
    the transaction.
    """
    statement = (
        pg_insert(RfqPushLog)
        .values(request_id=request_id, company_id=company_id, score=score, rank=rank)
        .on_conflict_do_nothing(constraint="uq_rfq_push_target")
        .returning(RfqPushLog.id)
    )
    inserted = db.execute(statement).scalar_one_or_none()
    db.flush()
    return inserted is not None


def list_pushed(db: Session, request_id: int) -> list[PushedSupplier]:
    """Suppliers notified about this RFQ, best rank first (staff panel).

    The score/rank come from the log rather than being recomputed: the weights
    change over time, and a rank re-derived today would not explain a push made
    last month.
    """
    rows = (
        db.query(RfqPushLog, Company)
        .join(Company, Company.id == RfqPushLog.company_id)
        .filter(RfqPushLog.request_id == request_id)
        .order_by(RfqPushLog.rank)
        .all()
    )
    return [
        PushedSupplier(
            company_id=log.company_id,
            company_name=company.legal_name or company.short_name or company.tax_id,
            score=log.score,
            rank=log.rank,
            notified_at=log.notified_at,
        )
        for log, company in rows
    ]
