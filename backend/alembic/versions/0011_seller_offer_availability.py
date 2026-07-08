"""Add availability ("в наличии" / "под заказ") to seller_offers (Phase 2).

Adds one ENUM type (offer_availability) and a non-nullable column on seller_offers
defaulting to in_stock, so every existing row is backfilled to «в наличии».

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-07

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. ENUM type (must precede the column) ────────────────────────────────
    offer_availability = postgresql.ENUM(
        "in_stock", "on_order", name="offer_availability"
    )
    offer_availability.create(op.get_bind())

    # ── 2. seller_offers.availability ─────────────────────────────────────────
    # Non-nullable with a server_default so existing rows backfill to «в наличии».
    op.add_column(
        "seller_offers",
        sa.Column(
            "availability",
            postgresql.ENUM(name="offer_availability", create_type=False),
            nullable=False,
            server_default="in_stock",
        ),
    )


def downgrade() -> None:
    op.drop_column("seller_offers", "availability")
    sa.Enum(name="offer_availability").drop(op.get_bind(), checkfirst=True)
