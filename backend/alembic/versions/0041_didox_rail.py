"""Didox document rail + sample commitment letter (P7.a Stage 2 — W2).

  enums  sample_request_status += 'pending_letter'
  tables didox_documents, didox_companies
  alter  contracts        += signing_provider
         contract_templates += kind
         seller_offers    += ikpu_* (5) + sample_letter_required/_terms
         sample_requests  += public_id, deal_id, letter_* (7)
         uq_sample_request_active — predicate now counts 'pending_letter'

`didox_documents` holds BOTH «Договор НК» (007) and ЭСФ (002). The ЭСФ has no
`contracts` row to hang off, and the lifecycle is identical either way, so one
table means one writer, one archive discipline and one status-50 handler. Its
`status` is Didox's own number stored verbatim as a smallint — their ladder is
theirs to extend and there is no invariant of ours for a PG enum to protect.

The archive pair lives on `didox_documents` rather than on `contracts` (a
deliberate deviation from .planning/deal-lifecycle/P7-PROVIDERS-LIVE.md §P7.a,
which predates the ЭСФ being in scope). The decision it recorded still holds:
the provider archive is a SECOND artefact with its OWN hash and never overwrites
`contracts.generated_document_path` / `document_sha256`.

Every column added to `seller_offers` and `sample_requests` is nullable or has a
server default: both are live tables, and `seller_offers` is fed by two origins
(Telegram sellers and portal companies).

`sample_requests.public_id` is NOT NULL with a volatile default, so Postgres
rewrites the table filling a distinct UUID per row — intended, and cheap at this
table's size. The letter's S3 key hangs off it so a signed legal artefact does
not carry our row count in its filename.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-18

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_SAMPLE_OLD = "status IN ('requested', 'accepted', 'sent')"
_ACTIVE_SAMPLE_NEW = "status IN ('pending_letter', 'requested', 'accepted', 'sent')"


def upgrade() -> None:
    # ── 1. sample_request_status += 'pending_letter' ──────────────────────────
    # ALTER TYPE … ADD VALUE cannot run inside a transaction block; Alembic wraps
    # each migration in one, so it is suspended here (same as 0004 and 0028).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE sample_request_status ADD VALUE IF NOT EXISTS 'pending_letter' BEFORE 'requested'"
        )

    # ── 2. didox_companies — can this company send documents at all? ──────────
    op.create_table(
        "didox_companies",
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("tin", sa.Text(), nullable=False),
        sa.Column("signup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("company_id"),
    )

    # ── 3. didox_documents — one row per Didox document, both types ───────────
    op.create_table(
        "didox_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("didox_id", sa.Text(), nullable=True),
        sa.Column("didox_contract_id", sa.Text(), nullable=True),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_company_id", sa.BigInteger(), nullable=False),
        sa.Column("partner_company_id", sa.BigInteger(), nullable=True),
        sa.Column("number", sa.Text(), nullable=True),
        sa.Column("doc_date", sa.Date(), nullable=True),
        sa.Column("status", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("status_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_archive_path", sa.Text(), nullable=True),
        sa.Column("provider_archive_sha256", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("doc_type IN ('007', '002')", name="ck_didox_document_type"),
        sa.CheckConstraint(
            "subject_kind IN ('contract', 'deal')", name="ck_didox_document_subject_kind"
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["partner_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique only when set: the row is committed BEFORE the create call, so a
    # create Didox accepted and we timed out on stays recoverable by `number`.
    op.create_index(
        "uq_didox_documents_didox_id",
        "didox_documents",
        ["didox_id"],
        unique=True,
        postgresql_where=sa.text("didox_id IS NOT NULL"),
    )
    # One LIVE document of a type per subject; a deleted draft frees the slot.
    op.create_index(
        "uq_didox_documents_subject",
        "didox_documents",
        ["subject_kind", "subject_id", "doc_type"],
        unique=True,
        postgresql_where=sa.text("status NOT IN (5, 55)"),
    )
    op.create_index("ix_didox_documents_poll", "didox_documents", ["status", "status_synced_at"])
    op.create_index("ix_didox_documents_deal", "didox_documents", ["deal_id", "id"])

    # ── 4. contracts.signing_provider — frozen at creation ────────────────────
    op.add_column(
        "contracts",
        sa.Column("signing_provider", sa.Text(), server_default="eimzo", nullable=False),
    )
    op.create_check_constraint(
        "ck_contract_signing_provider", "contracts", "signing_provider IN ('eimzo', 'didox')"
    )

    # ── 5. contract_templates.kind — the letter reuses this table ─────────────
    op.add_column(
        "contract_templates",
        sa.Column("kind", sa.Text(), server_default="contract", nullable=False),
    )
    op.create_check_constraint(
        "ck_contract_template_kind", "contract_templates", "kind IN ('contract', 'sample_letter')"
    )

    # ── 6. seller_offers: ИКПУ + commitment-letter terms ──────────────────────
    op.add_column("seller_offers", sa.Column("ikpu_code", sa.Text(), nullable=True))
    op.add_column("seller_offers", sa.Column("ikpu_name", sa.Text(), nullable=True))
    op.add_column("seller_offers", sa.Column("ikpu_package_code", sa.Text(), nullable=True))
    op.add_column("seller_offers", sa.Column("ikpu_package_name", sa.Text(), nullable=True))
    op.add_column("seller_offers", sa.Column("ikpu_origin", sa.SmallInteger(), nullable=True))
    op.add_column(
        "seller_offers", sa.Column("ikpu_synced_at", sa.DateTime(timezone=True), nullable=True)
    )
    # A half-filled ИКПУ builds a document Didox rejects at SEND time, after the
    # seller has already typed their key password. Fail in the form instead.
    op.create_check_constraint(
        "ck_offer_ikpu_complete",
        "seller_offers",
        "ikpu_code IS NULL OR (ikpu_package_code IS NOT NULL AND ikpu_origin IS NOT NULL)",
    )
    op.add_column(
        "seller_offers",
        sa.Column(
            "sample_letter_required", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column("seller_offers", sa.Column("sample_letter_terms", sa.Text(), nullable=True))

    # ── 7. sample_requests: identity, deal link, commitment letter ────────────
    op.add_column(
        "sample_requests",
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_sample_request_public_id", "sample_requests", ["public_id"])
    op.add_column("sample_requests", sa.Column("deal_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_sample_requests_deal", "sample_requests", "deals", ["deal_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("sample_requests", sa.Column("letter_number", sa.Text(), nullable=True))
    op.add_column("sample_requests", sa.Column("letter_storage_path", sa.Text(), nullable=True))
    op.add_column("sample_requests", sa.Column("letter_sha256", sa.Text(), nullable=True))
    op.add_column(
        "sample_requests",
        sa.Column("letter_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("sample_requests", sa.Column("letter_terms_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "sample_requests", sa.Column("letter_signature_evidence_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_sample_requests_letter_evidence",
        "sample_requests",
        "signature_evidence",
        ["letter_signature_evidence_id"],
        ["id"],
    )
    op.add_column(
        "sample_requests", sa.Column("letter_signed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # ── 8. An unsigned letter still holds the (offer, buyer) slot ─────────────
    op.drop_index("uq_sample_request_active", table_name="sample_requests")
    op.create_index(
        "uq_sample_request_active",
        "sample_requests",
        ["offer_id", "buyer_company_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_SAMPLE_NEW),
    )


def downgrade() -> None:
    op.drop_index("uq_sample_request_active", table_name="sample_requests")
    op.create_index(
        "uq_sample_request_active",
        "sample_requests",
        ["offer_id", "buyer_company_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_SAMPLE_OLD),
    )

    op.drop_constraint("fk_sample_requests_letter_evidence", "sample_requests", type_="foreignkey")
    op.drop_constraint("fk_sample_requests_deal", "sample_requests", type_="foreignkey")
    op.drop_constraint("uq_sample_request_public_id", "sample_requests", type_="unique")
    for column in (
        "letter_signed_at",
        "letter_signature_evidence_id",
        "letter_terms_snapshot",
        "letter_variables",
        "letter_sha256",
        "letter_storage_path",
        "letter_number",
        "deal_id",
        "public_id",
    ):
        op.drop_column("sample_requests", column)

    op.drop_constraint("ck_offer_ikpu_complete", "seller_offers", type_="check")
    for column in (
        "sample_letter_terms",
        "sample_letter_required",
        "ikpu_synced_at",
        "ikpu_origin",
        "ikpu_package_name",
        "ikpu_package_code",
        "ikpu_name",
        "ikpu_code",
    ):
        op.drop_column("seller_offers", column)

    op.drop_constraint("ck_contract_template_kind", "contract_templates", type_="check")
    op.drop_column("contract_templates", "kind")

    op.drop_constraint("ck_contract_signing_provider", "contracts", type_="check")
    op.drop_column("contracts", "signing_provider")

    op.drop_table("didox_documents")
    op.drop_table("didox_companies")

    # `pending_letter` is NOT removed from sample_request_status: PostgreSQL has
    # no ALTER TYPE … DROP VALUE, and recreating the type would require rewriting
    # every dependent column. A spare label costs nothing; rows still carrying it
    # would be the real problem, and this migration cannot invent a status for them.
