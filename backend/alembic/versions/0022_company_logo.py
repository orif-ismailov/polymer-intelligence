"""Company logo (P1 W1 — T1.1).

Adds (TZ block F, FR-M1):
  column  companies.logo_storage_path text NULL — S3 key of the company logo.

Only the object key is stored; the browser never gets a permanent public URL
(FR-M4), so the API hands out a short-lived presigned link per request instead.
Nullable because "no logo" is the normal state, not an error state.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-27

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("logo_storage_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "logo_storage_path")
