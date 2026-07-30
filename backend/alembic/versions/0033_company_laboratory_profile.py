"""Company laboratory profile + accreditation document kind.

  alter  companies += laboratory_profile
  alter  verification_document_kind += accreditation_certificate

The laboratory registration mockup (`docs/new-design/labaratory_reg_flow.jpeg`)
asks for city, website, email, phone, description on «Основная информация»,
plus accreditation paperwork (ISO 17025 / registration / accreditation). The
lab-only contact facts are never filtered on and other account types leave them
NULL, so they land as a JSONB blob — same pattern as `manufacturer_profile`
(0031) and `logistics_profile` (0032).

`iso_certificate` / `registration_certificate` already cover two of the
accreditation slots; `accreditation_certificate` is the missing third.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-30

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_DOC_KINDS = ("accreditation_certificate",)


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "laboratory_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # ALTER TYPE … ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for kind in _NEW_DOC_KINDS:
            op.execute(
                sa.text(
                    f"ALTER TYPE verification_document_kind ADD VALUE IF NOT EXISTS '{kind}'"
                )
            )


def downgrade() -> None:
    op.drop_column("companies", "laboratory_profile")
    # PG enum values cannot be removed safely — leave accreditation_certificate.
