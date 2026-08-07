"""Backfill: confirm the declared business roles of already-verified companies.

Data-only. Until now nothing in app code ever wrote `confirmed` — companies
registered with `declared` roles, verification approved the company but left the
roles untouched, so every confirmed-gated surface (lab/logistics pools, public
directories, role badges, RFQ-push audience) silently saw an empty set. From this
revision on, `verification_service._finalize_approval` confirms roles at
approval; this migration gives companies verified BEFORE that change the same
treatment. `confirmed_by` stays NULL — no staff actor is attributable in bulk.

Suspended/rejected companies keep `declared`: every confirmed-gate also requires
`status='verified'`, so confirming them would change nothing today and would lie
about what was vouched for.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-07

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE company_business_roles cbr
            SET status = 'confirmed'
            FROM companies c
            WHERE c.id = cbr.company_id
              AND c.status = 'verified'
              AND cbr.status = 'declared'
            """
        )
    )


def downgrade() -> None:
    # Irreversible on purpose: after the flip, rows confirmed by this backfill
    # are indistinguishable from rows confirmed by an actual approval
    # (`confirmed_by` is NULL on the auto-approve path too). Reverting would
    # un-confirm real approvals.
    pass
