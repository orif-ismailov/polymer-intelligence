"""Make seller_offers.price and qty_available nullable ("под заказ" = price on request).

Made-to-order offers («под заказ» / on_order) have no fixed stock quantity and no unit
price — the price is "по запросу". This drops NOT NULL on both columns so those offers
store NULL; in-stock offers keep a positive value (enforced in the API schema, not the DB).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-15

Safe migration: DROP NOT NULL only — no data rewrite, no default, no downtime.
IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "seller_offers", "qty_available", existing_type=sa.Numeric(14, 3), nullable=True
    )
    op.alter_column(
        "seller_offers", "price", existing_type=sa.Numeric(14, 2), nullable=True
    )


def downgrade() -> None:
    # NOTE: fails if any on_order offer has a NULL price/qty (expected — the feature
    # relies on nullability). Backfill before downgrading if that ever matters.
    op.alter_column(
        "seller_offers", "price", existing_type=sa.Numeric(14, 2), nullable=False
    )
    op.alter_column(
        "seller_offers", "qty_available", existing_type=sa.Numeric(14, 3), nullable=False
    )
