"""Operator-authored LLM prompt versions.

The news prompt was editable only by a developer with a commit and a deploy: the
`news_prompt_version` switch let an operator CHOOSE between `v1`, `v2` and `v3`,
but those three are files baked into the image. This table is where a version
authored from the admin panel lives.

It does not weaken the rule the repo states in five places. "Prompts are
versioned and immutable" protects one property — **a version string always means
one text** — and that is exactly what an append-only table gives: saving an edit
writes `v4`, it never rewrites `v3`. Editing in place would have broken it in a
way nothing could see, because `load_news_prompt` caches per process on the
version string alone: workers holding `v3` would keep the old text while
restarted ones took the new, and both would journal `prompt_version="v3"` into
`parse_runs` with nothing able to say which article got which text.

So there is NO `updated_at` and no UPDATE path anywhere in the codebase, the same
shape and for the same reason as `registry_snapshots` (migration 0029): a change
is a new row, and the history of a prompt IS the sequence of its rows.

The shipped `parsing/prompts/news_extract_v*.md` files are NOT seeded here. They
stay the fallback, and the presence of a row is what distinguishes "an operator
wrote this" from "the image shipped it" — the same split `substances.seed_revision`
draws, where NULL means hands off, this is the operator's now.

Columns:
  family       which prompt this is a version of. `Text` + CHECK rather than a PG
               enum, because Postgres has no ALTER TYPE … DROP VALUE and the
               families are also plain constants in service code. One value today
               (`news_extract`); the column exists so the other four families can
               join without a migration that reshapes the table.
  version      the string journalled into `parse_runs.prompt_version`. Unique per
               family, and never reused: that column is the only record of which
               text produced a past classification.
  body         the prompt itself, in Postgres rather than S3. `Report.content_md`
               is the precedent; a few kilobytes read once per process does not
               want an object store, and `contract_templates` — which does use
               S3 — keeps only the CURRENT body, which is the mistake this table
               exists not to make.
  body_sha256  dedup. Re-saving unchanged text returns the existing version
               instead of minting v5, v6, v7 from an operator pressing Save
               twice — the `raw_items` idiom, where the content hash is what makes
               a repeat a no-op rather than a duplicate.
  created_by   who wrote it. Nullable for the same reason as `audit_log`: a row
               written by a script or a migration has no staff member.

Which version is LIVE is not stored here — that is the existing
`news_prompt_version` setting, so activation reuses the whole override rail
(validation, audit, the Redis generation bump, cross-process propagation).

Revision ID: 0046
Revises: 0045
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_sha256", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # A version string is the only handle a `parse_runs` row has on the text
        # that produced it, so it must identify exactly one body forever.
        sa.UniqueConstraint("family", "version", name="uq_prompt_version"),
        # Saving unchanged text is a no-op, not a new version.
        sa.UniqueConstraint("family", "body_sha256", name="uq_prompt_body"),
        sa.CheckConstraint("family IN ('news_extract')", name="ck_prompt_family"),
        # Refused at the write too, with a message an operator can read — but an
        # empty prompt is a VALID system prompt, which is what made the loader's
        # old `return ""` invisible, so the schema says it as well.
        sa.CheckConstraint("length(btrim(body)) > 0", name="ck_prompt_body_not_blank"),
    )
    # Every read is "the versions of this family, newest first".
    op.create_index("ix_prompt_versions_family", "prompt_versions", ["family", "id"])
    # Deliberately no `updated_at` and no index on it: there is no update path.


def downgrade() -> None:
    """Drop the authored versions.

    The shipped `news_extract_v*.md` files are untouched by this table's
    existence, so the news pipeline keeps working — but any prompt an operator
    wrote is gone, and a `news_prompt_version` override pointing at one of them
    will fail to load. Capture them first, and put the switch back to a shipped
    version, before downgrading:

        SELECT version, body FROM prompt_versions WHERE family = 'news_extract';
    """
    op.drop_index("ix_prompt_versions_family", table_name="prompt_versions")
    op.drop_table("prompt_versions")
