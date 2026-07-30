"""Company manufacturer profile + factory document kinds.

  alter  companies += actual_address, registration_number, manufacturer_profile
  alter  verification_document_kind += production_license, export_license,
         certificate_of_origin, iso_certificate, compliance_certificate

The manufacturer registration mockup (`docs/new-design/companys_list.jpeg`) asks
for a factory address, a company registration number, production facts (capacity,
lines, markets, ISO) and buyer terms (MOQ, financial toggles). Those do not fit
the existing declared-profile columns, so:

* `actual_address` / `registration_number` land as plain text columns (queried /
  shown next to legal_address / tax_id).
* The rest of the manufacturer-only questionnaire is a JSONB blob
  (`manufacturer_profile`) — free-form facts that are never filtered on and that
  other account types leave NULL.

The six factory certificate slots on step 5 need distinct document kinds so the
upload rows round-trip; they extend `verification_document_kind`.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-30

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_DOC_KINDS = (
    "production_license",
    "export_license",
    "certificate_of_origin",
    "iso_certificate",
    "compliance_certificate",
)


def upgrade() -> None:
    op.add_column("companies", sa.Column("actual_address", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("registration_number", sa.Text(), nullable=True))
    op.add_column(
        "companies",
        sa.Column(
            "manufacturer_profile",
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
    op.drop_column("companies", "manufacturer_profile")
    op.drop_column("companies", "registration_number")
    op.drop_column("companies", "actual_address")
    # PG enum values cannot be removed safely — leave the five kinds in place.
