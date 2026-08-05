"""Company media — image blobs a company's public profile references.

Distinct from `companies.logo_storage_path` and `cover_storage_path`, which are
1:1 with the company and need no table. This is for images there can be several
of, currently the «Наши возможности» thumbnails on a carrier profile.

Content-addressed by id, NOT slotted. An earlier design keyed rows on
`(company_id, kind, slot)` and had `slot` mirror an index into the JSONB
capability array — which meant the two had to be kept in step in two places and
every reorder orphaned a row. Here the JSONB stays the ordering authority and
holds `{capability_key: media_id}`; a media row is just bytes with an owner.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class CompanyMedia(Base):
    """One uploaded image belonging to a company."""

    __tablename__ = "company_media"
    __table_args__ = (Index("ix_company_media_company", "company_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
