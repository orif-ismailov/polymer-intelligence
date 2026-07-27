"""RFQ supplier-push log (R4 / P4 — T3.1).

  table rfq_push_log (request_id, company_id, score, rank, notified_at)

The unique index on (request_id, company_id) IS the dedup rule (FR-A2): the push
task inserts with ON CONFLICT DO NOTHING, so re-running it — after a retry, or
because the RFQ was edited — notifies nobody twice.

`score` and `rank` are stored, not recomputed. Staff read this log to answer "why
did we push this RFQ to them?", and the weights will change over time; a rank
re-derived with today's weights would not explain a push made last month.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-27

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rfq_push_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "notified_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "company_id", name="uq_rfq_push_target"),
    )
    op.create_index("ix_rfq_push_log_request", "rfq_push_log", ["request_id", "rank"])


def downgrade() -> None:
    op.drop_index("ix_rfq_push_log_request", table_name="rfq_push_log")
    op.drop_table("rfq_push_log")
