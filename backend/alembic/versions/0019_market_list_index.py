"""Market list index (R2 W6 T6.2).

Adds ``ix_seller_offers_status_published`` on ``seller_offers(status, published_at)``
to back the portal + webapp market list (``WHERE status='approved' ORDER BY
published_at DESC``), which was a Seq Scan + Sort before.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_seller_offers_status_published",
        "seller_offers",
        ["status", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_seller_offers_status_published", table_name="seller_offers")
