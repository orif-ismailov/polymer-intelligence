"""The Central Bank's bank-branch register, as a reference table.

`company_bank_accounts.bank_name` has always been free text that somebody typed,
next to a `bank_mfo` validated for SHAPE in four places and for EXISTENCE in none.
The Didox registry prefill cannot help: `/v1/utils/info/{tin}` returns the MFO and
the account number and carries no bank name at all.

The CB publishes the join — «Код филиала» IS the 5-digit MFO — so these two tables
hold it:

  * `bank_branches` — one row per branch, `mfo` UNIQUE as the natural key, exactly
    like `products.code` and `substances.code`. `String(5)` to match
    `company_bank_accounts.bank_mfo`, the column it exists to name.
  * `bank_register_imports` — one row per load, so an operator can see which file
    the list came from and how old the CB's own publication is. `uploaded_by` is
    NULL for the copy shipped with the release.

The register is republished periodically and is reloaded from the admin panel
rather than through a deploy, which is why the provenance is a table rather than a
constant in the source.

`import_id` cascades: an import row and the branches it wrote are one fact, and a
load replaces the whole table in a single transaction.

Revision ID: 0051
Revises: 0050
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_register_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_created_at", sa.Date(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_by", sa.BigInteger(), sa.ForeignKey("staff_users.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "bank_branches",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("mfo", sa.String(length=5), nullable=False),
        sa.Column("bank_name", sa.Text(), nullable=False),
        sa.Column("branch_name", sa.Text(), nullable=True),
        sa.Column("branch_type", sa.String(length=1), nullable=True),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            sa.ForeignKey("bank_register_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    # The lookup is "one MFO → one bank name", on every keystroke of a 5-digit
    # field, so the key it is read by is both unique and indexed.
    op.create_index("uq_bank_branches_mfo", "bank_branches", ["mfo"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_bank_branches_mfo", table_name="bank_branches")
    op.drop_table("bank_branches")
    op.drop_table("bank_register_imports")
