"""Company term presets, contracts as data, and several ЭСФ per contract.

Three changes, one reason — a contract's terms are worth more than the PDF they
are printed in:

* `contract_term_presets` — a company's saved commercial terms («шаблон условий»):
  payment, delivery, Incoterms, special conditions. The legal text stays the
  platform's template; this is what a company repeats from one contract to the next.
* `contracts.{currency, incoterms, payment_terms, delivery_window, amount_total,
  term_preset_id}` + `contract_lines`, and `didox_document_lines` — the agreed and
  the invoiced goods as numbers rather than strings inside `variables` JSONB, for
  the market analytics to come.
* `uq_didox_documents_subject` now binds the договор only. Goods ship in parts, and
  each shipment is its own ЭСФ against the same contract.

Existing contracts are backfilled from `variables`. The parse is copied here rather
than imported — a migration must keep meaning what it meant when it was written.

Revision ID: 0053
Revises: 0052
"""

from __future__ import annotations

import decimal

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def _number(raw: object) -> decimal.Decimal | None:
    text = str(raw or "").replace(",", ".").replace(" ", "").replace(" ", "")
    if not text:
        return None
    try:
        value = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return None
    return value if value.is_finite() else None


def _text(raw: object) -> str | None:
    value = str(raw or "").strip()
    return value or None


def upgrade() -> None:
    op.create_table(
        "contract_term_presets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "terms", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_by_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_contract_term_presets_company_id", "contract_term_presets", ["company_id"]
    )
    op.create_index(
        "uq_contract_term_preset_name",
        "contract_term_presets",
        ["company_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.add_column(
        "contracts",
        sa.Column(
            "term_preset_id",
            sa.BigInteger(),
            sa.ForeignKey("contract_term_presets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    for column in ("currency", "incoterms", "payment_terms", "delivery_window"):
        op.add_column("contracts", sa.Column(column, sa.Text(), nullable=True))
    op.add_column("contracts", sa.Column("amount_total", sa.Numeric(18, 2), nullable=True))

    op.create_table(
        "contract_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "contract_id",
            sa.BigInteger(),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord_no", sa.SmallInteger(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("ikpu_code", sa.Text(), nullable=True),
        sa.Column("ikpu_name", sa.Text(), nullable=True),
        sa.Column("package_code", sa.Text(), nullable=True),
        sa.Column("package_name", sa.Text(), nullable=True),
        sa.Column("qty", sa.Numeric(18, 3), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(18, 3), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("vat_rate", sa.SmallInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.UniqueConstraint("contract_id", "ord_no", name="uq_contract_line_ord"),
    )

    op.create_table(
        "didox_document_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "didox_document_id",
            sa.BigInteger(),
            sa.ForeignKey("didox_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord_no", sa.SmallInteger(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("ikpu_code", sa.Text(), nullable=False),
        sa.Column("ikpu_name", sa.Text(), nullable=False),
        sa.Column("package_code", sa.Text(), nullable=False),
        sa.Column("package_name", sa.Text(), nullable=False),
        sa.Column("qty", sa.Numeric(18, 6), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_rate", sa.SmallInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_sum", sa.Numeric(18, 2), nullable=False),
        sa.Column("origin", sa.SmallInteger(), nullable=True),
    )
    op.create_index(
        "ix_didox_document_lines_didox_document_id",
        "didox_document_lines",
        ["didox_document_id"],
    )

    op.drop_index("uq_didox_documents_subject", table_name="didox_documents")
    op.create_index(
        "uq_didox_documents_subject",
        "didox_documents",
        ["subject_kind", "subject_id", "doc_type"],
        unique=True,
        postgresql_where=sa.text("status NOT IN (5, 55) AND doc_type = '007'"),
    )
    op.create_index(
        "ix_didox_documents_subject",
        "didox_documents",
        ["subject_kind", "subject_id", "doc_type"],
    )

    _backfill()


def _backfill() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, title, variables FROM contracts")).mappings().all()
    for row in rows:
        variables = row["variables"] if isinstance(row["variables"], dict) else {}
        qty = _number(variables.get("qty"))
        price = _number(variables.get("price"))
        amount = (qty * price).quantize(decimal.Decimal("0.01")) if qty is not None and price is not None else None
        currency = _text(variables.get("currency"))
        conn.execute(
            sa.text(
                "UPDATE contracts SET currency = :currency, incoterms = :incoterms, "
                "payment_terms = :payment_terms, delivery_window = :delivery_window, "
                "amount_total = :amount WHERE id = :id"
            ),
            {
                "id": row["id"],
                "currency": currency,
                "incoterms": _text(variables.get("incoterms")),
                "payment_terms": _text(variables.get("payment_terms")),
                "delivery_window": _text(variables.get("delivery_window")),
                "amount": amount,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO contract_lines "
                "(contract_id, ord_no, product_name, qty, unit, price, currency, amount) "
                "VALUES (:id, 1, :name, :qty, :unit, :price, :currency, :amount)"
            ),
            {
                "id": row["id"],
                "name": _text(variables.get("product")) or row["title"],
                "qty": qty,
                "unit": _text(variables.get("unit")),
                "price": price,
                "currency": currency,
                "amount": amount,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_didox_documents_subject", table_name="didox_documents")
    op.drop_index("uq_didox_documents_subject", table_name="didox_documents")
    op.create_index(
        "uq_didox_documents_subject",
        "didox_documents",
        ["subject_kind", "subject_id", "doc_type"],
        unique=True,
        postgresql_where=sa.text("status NOT IN (5, 55)"),
    )
    op.drop_table("didox_document_lines")
    op.drop_table("contract_lines")
    for column in (
        "amount_total",
        "delivery_window",
        "payment_terms",
        "incoterms",
        "currency",
        "term_preset_id",
    ):
        op.drop_column("contracts", column)
    op.drop_table("contract_term_presets")
