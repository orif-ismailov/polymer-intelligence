"""Company logistics profile + carrier document kinds.

  alter  companies += logistics_profile
  alter  verification_document_kind += carrier_license, liability_insurance,
         service_contract

The logistics registration mockup (`docs/new-design/logist_reg_flow.jpeg`) asks
for services, geography (from/to countries + popular routes), cargo
specialisation, company capabilities, a tariff model, and carrier paperwork.
Those facts are never filtered on and other account types leave them NULL, so
they land as a JSONB blob — same pattern as `manufacturer_profile` (0031).

Three document kinds cover the mockup slots that are not already in the enum
(`license`/`certificate`/`iso_certificate`/`bank_letter` remain reused where
labels match).

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-30

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_DOC_KINDS = (
    "carrier_license",
    "liability_insurance",
    "service_contract",
)


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "logistics_profile",
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
    op.drop_column("companies", "logistics_profile")
    # PG enum values cannot be removed safely — leave the three kinds in place.
