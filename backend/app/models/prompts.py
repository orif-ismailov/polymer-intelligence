"""
Operator-authored LLM prompt versions (migration 0046).

APPEND-ONLY. There is no `updated_at` and no code path anywhere that UPDATEs a
row: a change to a prompt is a new version, never a rewrite of an old one. That
is the whole design, and it is not a stylistic preference —
`parsing.news_extractor.load_news_prompt` caches per process keyed on the version
string, so a mutable body would leave workers that already loaded `v3` running
the old text while restarted ones ran the new, with every `parse_runs` row from
both saying `prompt_version="v3"`.

The shipped `parsing/prompts/news_extract_v*.md` files are not rows here. They
remain the fallback, and the presence of a row is what says an operator wrote
this one — the same distinction `substances.seed_revision` draws between a seeded
value and a corrected one.

Which version is LIVE is not here either: that is the `news_prompt_version`
setting, so activating a version is an ordinary settings override and inherits
its validation, audit row and cross-process propagation.

Kernel, not a domain: prompts are configuration substrate shared by `parsing/`
and the admin API, with no bounded context of their own.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

#: The one prompt family an operator can author today. `Text` + CHECK rather than
#: a PG enum — Postgres has no `ALTER TYPE … DROP VALUE`, and the four other
#: families (`extract`, `report`, `analyze_request`, `substance_match`) can join
#: by widening the constraint rather than reshaping the table.
FAMILY_NEWS_EXTRACT = "news_extract"
FAMILIES: tuple[str, ...] = (FAMILY_NEWS_EXTRACT,)


class PromptVersion(Base):
    """One immutable version of a prompt, written from the admin panel."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        # A version string is the only handle a `parse_runs` row has on the text
        # that produced it. It must identify exactly one body, forever.
        UniqueConstraint("family", "version", name="uq_prompt_version"),
        # Saving unchanged text is a no-op, not a new version — the `raw_items`
        # content-hash idiom, so an operator pressing Save twice does not mint
        # v5, v6, v7 that differ in nothing.
        UniqueConstraint("family", "body_sha256", name="uq_prompt_body"),
        CheckConstraint(
            "family IN (" + ", ".join(f"'{f}'" for f in FAMILIES) + ")",
            name="ck_prompt_family",
        ),
        # An empty string is a VALID system prompt — the model simply gets no
        # instructions — which is precisely why the old loader's `return ""` was
        # invisible. Refused at the write with a readable message, and here too.
        CheckConstraint("length(btrim(body)) > 0", name="ck_prompt_body_not_blank"),
        Index("ix_prompt_versions_family", "family", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    family: Mapped[str] = mapped_column(Text, nullable=False)
    #: Journalled verbatim into `parse_runs.prompt_version`, and never reused.
    version: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    #: Why this version exists, in the author's words. Optional, and the only
    #: place that reason is recorded — the audit row carries the version and its
    #: size, deliberately not its text.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
