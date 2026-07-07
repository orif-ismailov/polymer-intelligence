"""Buyer→offer inquiries: offer_requests table + offer_request_status enum.

Adds the "Request an offer" brokerage flow. A buyer submits an inquiry (qty /
target price / message) against a specific approved seller offer; it lands in
`pending` for admin review and, on approval, is forwarded to the seller by bot DM.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-06

IMPORTANT: Schema/data changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the ENUM type explicitly (idempotent), then reference it in the
    # column with create_type=False so op.create_table does NOT try to CREATE
    # TYPE a second time — that double-create fails on a fresh DB with
    # DuplicateObject. Mirrors the correct pattern in 0007_marketplace.py.
    offer_request_status = postgresql.ENUM(
        "pending", "approved", "rejected", name="offer_request_status"
    )
    offer_request_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "offer_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "offer_id",
            sa.Integer(),
            sa.ForeignKey("seller_offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("qty_unit", sa.String(8), nullable=False, server_default="MT"),
        sa.Column("target_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="offer_request_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "moderated_by",
            sa.Integer(),
            sa.ForeignKey("staff_users.id"),
            nullable=True,
        ),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_offer_requests_offer_id", "offer_requests", ["offer_id"])
    op.create_index("ix_offer_requests_client_id", "offer_requests", ["client_id"])
    op.create_index("ix_offer_requests_status", "offer_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_offer_requests_status", table_name="offer_requests")
    op.drop_index("ix_offer_requests_client_id", table_name="offer_requests")
    op.drop_index("ix_offer_requests_offer_id", table_name="offer_requests")
    op.drop_table("offer_requests")
    sa.Enum(name="offer_request_status").drop(op.get_bind(), checkfirst=True)
