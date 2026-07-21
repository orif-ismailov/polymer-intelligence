"""Add sources.group_name (operator source groups, Phase 8f-2).

Lets operators organize sources into named groups (e.g. "Uzbek news", "Global news",
"Exchange") and manage them from the dashboard. Nullable text — ungrouped sources keep
NULL. No behavioral change to ingestion; grouping is organizational only.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-21

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("group_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "group_name")
