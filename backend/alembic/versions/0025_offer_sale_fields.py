"""Offer sale fields + favorites (R4 / P4 — T1.1).

Two small, unrelated additions to the offer surface:

  enum   offer_sale_mode (from_stock, made_to_order, recurring_contract)
  alter  seller_offers += lead_time_days, sale_mode,
         accepts_rfq / accepts_contract / accepts_escrow
  table  offer_favorites (one row per account+offer)

`seller_offers` is a live table carrying rows from two origins (TG sellers and
portal companies), so every added column is nullable or has a server default — a
bare NOT NULL would fail the migration on any real database.

`accepts_rfq` defaults TRUE and the other two FALSE: answering an RFQ costs a
seller nothing, while signing a contract or holding money in escrow are
commitments nobody should be opted into retroactively.

`offer_favorites` is keyed to the account, not the company — a shortlist is
personal, and switching company hats in the portal must not change it.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-27

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SALE_MODE = ("from_stock", "made_to_order", "recurring_contract")


def upgrade() -> None:
    postgresql.ENUM(*_SALE_MODE, name="offer_sale_mode").create(op.get_bind())

    op.add_column("seller_offers", sa.Column("lead_time_days", sa.Integer(), nullable=True))
    op.add_column(
        "seller_offers",
        sa.Column(
            "sale_mode",
            postgresql.ENUM(name="offer_sale_mode", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "seller_offers",
        sa.Column("accepts_rfq", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "seller_offers",
        sa.Column(
            "accepts_contract", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "seller_offers",
        sa.Column(
            "accepts_escrow", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    op.create_table(
        "offer_favorites",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_account_id", "offer_id", name="uq_offer_favorite"),
    )
    op.create_index("ix_offer_favorites_account", "offer_favorites", ["user_account_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_offer_favorites_account", table_name="offer_favorites")
    op.drop_table("offer_favorites")

    for column in (
        "accepts_escrow",
        "accepts_contract",
        "accepts_rfq",
        "sale_mode",
        "lead_time_days",
    ):
        op.drop_column("seller_offers", column)

    postgresql.ENUM(name="offer_sale_mode").drop(op.get_bind())
