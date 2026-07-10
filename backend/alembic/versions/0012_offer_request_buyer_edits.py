"""Buyer-editable offer inquiries: edited_at + last_change_summary + seller_notified.

Lets a buyer revise a submitted "Request an offer" inquiry. An edit to an
already-forwarded inquiry re-enters moderation and, on re-approval, re-notifies the
seller with a diff of what changed. All three columns are additive and nullable
(seller_notified defaults false), so existing rows need no backfill.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offer_requests",
        sa.Column("edited_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "offer_requests",
        sa.Column("last_change_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "offer_requests",
        sa.Column(
            "seller_notified", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("offer_requests", "seller_notified")
    op.drop_column("offer_requests", "last_change_summary")
    op.drop_column("offer_requests", "edited_at")
