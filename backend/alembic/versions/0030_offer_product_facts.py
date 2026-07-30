"""Offer product facts — manufacturer, key properties, applications.

  alter  seller_offers += manufacturer, key_properties, applications

The redesigned product-creation flow (`docs/new-design/product_creation.jpeg`)
asks for three facts the offer row could not hold: who made the goods
(«Производитель: Sibur»), the spec chips «Ключевые свойства» (MFI, плотность,
…) and the «Применение» chips (литьё под давлением, упаковка, …). They were the
only fields on those sheets with nowhere to land, and folding them into
`description` would have made them unreadable back out — the preview sheet and
the product page render each chip as its own pill.

Both chip sets are JSONB arrays of short strings rather than a join table: they
are free text a seller types, never queried by value, and a normalized table
would buy nothing but two more joins on every card render. `manufacturer` is
Text and NOT a link to `companies` — the maker of the goods is usually not a
party on this platform.

`seller_offers` is a live table carrying rows from two origins (TG sellers and
portal companies), so all three columns are nullable.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-30

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("seller_offers", sa.Column("manufacturer", sa.Text(), nullable=True))
    op.add_column(
        "seller_offers",
        sa.Column("key_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "seller_offers",
        sa.Column("applications", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seller_offers", "applications")
    op.drop_column("seller_offers", "key_properties")
    op.drop_column("seller_offers", "manufacturer")
