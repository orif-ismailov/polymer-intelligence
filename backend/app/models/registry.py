"""State-registry evidence (R6 / P7.c — T4.1).

One table, one idea: **what a registry told us about a company is evidence, and
evidence is immutable.** `registry_snapshots` has no `updated_at` and no update
path anywhere in the codebase. A fresh check is a new row; the history of a
company's registry checks IS the sequence of its rows.

That is load-bearing rather than stylistic, because two very different things
write these rows:

  * `source='registry'` — an API answered. Today that means nothing: the only
    official channel for a private company is ПЦД, whose access process is not
    normatively formalised (INTEGRATIONS.md §3). `created_by` is NULL, because
    nobody asserted anything.
  * `source='manual'` — an operator read an open service (my.soliq.uz for the VAT
    register, license.gov.uz for licences), transcribed the result and attached a
    screenshot. INTEGRATIONS.md §3 sanctions this as the pre-ПЦД bridge, and it
    is the half of P7.c that works today. `created_by` is the staff member whose
    name is on the claim.

Overwriting a row would erase which of the two said what, and when — exactly the
question an auditor asks. The screenshot gets the same treatment as a PKCS#7 in
`signature_evidence`: a storage key plus the sha256 of the bytes.

`kind` and `source` are Text + CHECK rather than PG enums, matching
`escrow_payments.mode`: small closed sets whose members are also plain constants
in service code.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

#: One kind per `GovRegistryClient` lookup — the table mirrors the adapter, so a
#: manual transcription and an API answer are shaped alike.
SNAPSHOT_KIND_COMPANY = "company"
SNAPSHOT_KIND_LICENSES = "licenses"
SNAPSHOT_KIND_VAT = "vat"
SNAPSHOT_KINDS: tuple[str, ...] = (
    SNAPSHOT_KIND_COMPANY,
    SNAPSHOT_KIND_LICENSES,
    SNAPSHOT_KIND_VAT,
)

#: Who produced the snapshot. Never collapse these into one value: an operator's
#: reading of a public web page and a registry API's answer carry different
#: weight, and the difference has to survive in the record.
SNAPSHOT_SOURCE_REGISTRY = "registry"
SNAPSHOT_SOURCE_MANUAL = "manual"
SNAPSHOT_SOURCES: tuple[str, ...] = (SNAPSHOT_SOURCE_REGISTRY, SNAPSHOT_SOURCE_MANUAL)

#: `provider` values in use. Free text by design — a new ПЦД catalogue service is
#: a new string, not a migration.
PROVIDER_MANUAL = "manual"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class RegistrySnapshot(Base):
    """One immutable observation of a company in a state registry."""

    __tablename__ = "registry_snapshots"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_quoted(SNAPSHOT_KINDS)})", name="ck_registry_snapshot_kind"
        ),
        CheckConstraint(
            f"source IN ({_quoted(SNAPSHOT_SOURCES)})", name="ck_registry_snapshot_source"
        ),
        # "The latest snapshot of kind X for company Y" is the only read path.
        Index("ix_registry_snapshots_lookup", "company_id", "kind", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    #: Which registry/channel answered ('pcd', 'oneid', 'manual', …).
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    #: The normalized DTO (`CompanySnapshot`/`LicenseSnapshot[]`/`VatSnapshot`).
    #: NOT NULL — a snapshot with no content is not evidence of anything.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: What the registry called the state, verbatim, before we normalized it.
    raw_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The operator's screenshot (manual snapshots only) + the sha256 of its bytes.
    evidence_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The staff member who transcribed it. NULL when an API answered.
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    #: When the observation was made (an operator may transcribe a page they read
    #: earlier), as distinct from when the row was written.
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
