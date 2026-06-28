"""PetroAI buyer-wizard request fields: free-typed product + contact snapshot.

Phase 1 (unified Mini App, 5-step buyer wizard). Additive, low-risk:

  - requests.product_id  → drop NOT NULL (a buyer may type a product not in our
    catalog; the free-typed name goes in the new product_text column).
  - add requests.product_text, company_name, contact_name, phone, legal_address
    (all nullable TEXT) — the wizard's product + contact steps snapshot onto the
    request so the record is self-contained.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-28

IMPORTANT: Schema/data changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COLUMNS = ("product_text", "company_name", "contact_name", "phone", "legal_address")


def upgrade() -> None:
    # product_id becomes nullable (free-typed products carry no catalog id).
    op.alter_column("requests", "product_id", existing_type=sa.SmallInteger(), nullable=True)

    for col in _NEW_COLUMNS:
        op.add_column("requests", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    for col in reversed(_NEW_COLUMNS):
        op.drop_column("requests", col)

    # Restore NOT NULL. Any rows with a NULL product_id (free-typed products) must be
    # backfilled before downgrading; left to the operator since there is no safe default.
    op.alter_column("requests", "product_id", existing_type=sa.SmallInteger(), nullable=False)
