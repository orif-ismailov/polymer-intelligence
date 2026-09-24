"""Specifications of a framework contract — «Спецификация № N» (stage 2).

A framework contract (the AKFA 346-01 shape) names no goods: each shipment is a
specification, signed on its own, and invoiced by its own ЭСФ. This adds:

* `contract_specifications` — one row per specification, numbered within its
  contract, with the terms it was drawn up with and the totals it states;
* `contract_lines.specification_id` — the goods of a specification are contract
  lines like any other, so the analytics reads one table. The per-contract
  ordinal becomes unique per (contract, specification);
* `didox_documents`: doc type `000` («Произвольный документ», subtype 8
  «Спецификация» — it carries our PDF), subject kind `specification`, and
  `specification_id` on an ЭСФ issued against one;
* `contract_templates.kind = 'specification'` for the specification's own form.

Revision ID: 0054
Revises: 0053
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_specifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "contract_id",
            sa.BigInteger(),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("spec_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column(
            "variables", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("amount_without_vat", sa.Numeric(18, 2), nullable=True),
        sa.Column("vat_sum", sa.Numeric(18, 2), nullable=True),
        sa.Column("amount_with_vat", sa.Numeric(18, 2), nullable=True),
        sa.Column("generated_document_path", sa.Text(), nullable=True),
        sa.Column("document_sha256", sa.Text(), nullable=True),
        sa.Column("declined_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("contract_id", "number", name="uq_contract_specification_number"),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_signatures', 'active', 'declined', 'cancelled')",
            name="ck_contract_specification_status",
        ),
    )

    op.add_column(
        "contract_lines",
        sa.Column(
            "specification_id",
            sa.BigInteger(),
            sa.ForeignKey("contract_specifications.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.drop_constraint("uq_contract_line_ord", "contract_lines", type_="unique")
    op.create_index(
        "uq_contract_line_ord",
        "contract_lines",
        ["contract_id", sa.text("coalesce(specification_id, 0)"), "ord_no"],
        unique=True,
    )

    op.drop_constraint("ck_didox_document_type", "didox_documents", type_="check")
    op.create_check_constraint(
        "ck_didox_document_type", "didox_documents", "doc_type IN ('007', '002', '000')"
    )
    op.drop_constraint("ck_didox_document_subject_kind", "didox_documents", type_="check")
    op.create_check_constraint(
        "ck_didox_document_subject_kind",
        "didox_documents",
        "subject_kind IN ('contract', 'deal', 'specification')",
    )
    op.add_column(
        "didox_documents",
        sa.Column(
            "specification_id",
            sa.BigInteger(),
            sa.ForeignKey("contract_specifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.drop_constraint("ck_contract_template_kind", "contract_templates", type_="check")
    op.create_check_constraint(
        "ck_contract_template_kind",
        "contract_templates",
        "kind IN ('contract', 'sample_letter', 'specification')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contract_template_kind", "contract_templates", type_="check")
    op.create_check_constraint(
        "ck_contract_template_kind", "contract_templates", "kind IN ('contract', 'sample_letter')"
    )
    op.drop_column("didox_documents", "specification_id")
    op.drop_constraint("ck_didox_document_subject_kind", "didox_documents", type_="check")
    op.create_check_constraint(
        "ck_didox_document_subject_kind", "didox_documents", "subject_kind IN ('contract', 'deal')"
    )
    op.drop_constraint("ck_didox_document_type", "didox_documents", type_="check")
    op.create_check_constraint(
        "ck_didox_document_type", "didox_documents", "doc_type IN ('007', '002')"
    )
    op.drop_index("uq_contract_line_ord", table_name="contract_lines")
    op.create_unique_constraint(
        "uq_contract_line_ord", "contract_lines", ["contract_id", "ord_no"]
    )
    op.drop_column("contract_lines", "specification_id")
    op.drop_table("contract_specifications")
