"""The bank register: load it, and answer "which bank is this MFO?".

Separate from `service.py` (products) because it is a different dictionary with a
different lifecycle — products are edited a row at a time from the admin panel,
the bank register arrives whole from the Central Bank and is replaced whole.

**Order is the safety property.** `import_register` parses BEFORE it deletes
anything, so a truncated download or a wrong file leaves the working register
exactly as it was. Done the other way round, one bad upload would empty the table
and every MFO on every registration form would stop resolving — and the operator
would have no copy to put back. This is the same rule
`verification/api_admin.py` states for registry evidence: refuse before anything
is recorded.

Following `DEC-dep-owns-commit`: this module flushes, the caller commits.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domains.reference.bank_register import parse_register
from app.domains.reference.models import BankBranch, BankRegisterImport
from app.services import audit_service


@dataclass(frozen=True)
class ImportOutcome:
    """What one load did.

    `imported=False` means the same bytes were already live and nothing was
    touched — not a failure, and the reason the seeder can run on every deploy.
    """

    imported: bool
    row_count: int
    file_created_at: datetime.date | None
    sha256: str


def current_import(db: Session) -> BankRegisterImport | None:
    """The live register's provenance row, or None before the first load."""
    return db.execute(
        select(BankRegisterImport).order_by(BankRegisterImport.id.desc()).limit(1)
    ).scalar_one_or_none()


def bank_by_mfo(db: Session, mfo: str) -> BankBranch | None:
    """The branch for a 5-digit MFO, or None.

    No normalisation beyond a strip: the column is `String(5)` and every caller
    validates the shape first, so a value that is not five digits cannot match
    and does not need its own error.
    """
    return db.execute(
        select(BankBranch).where(BankBranch.mfo == mfo.strip())
    ).scalar_one_or_none()


def count(db: Session) -> int:
    """How many branches the live register holds."""
    return db.query(BankBranch).count()


def import_register(
    db: Session,
    content: bytes,
    filename: str,
    *,
    staff_user_id: int | None = None,
    force: bool = False,
) -> ImportOutcome:
    """Replace the register with the contents of `content`. Does NOT commit.

    Raises `BankRegisterInvalid` (a `ValueError`) before writing anything if the
    file is not a register we can trust — which is what keeps a rejected upload
    from emptying the table.

    Re-loading bytes that are already live is a no-op unless `force`, so the
    seeder is free to run on every deploy: it neither rewrites 324 rows nor adds
    a provenance row recording a change that did not happen.
    """
    digest = hashlib.sha256(content).hexdigest()

    # Parse FIRST. Everything below this line mutates.
    parsed = parse_register(content)

    live = current_import(db)
    if live is not None and live.sha256 == digest and not force:
        return ImportOutcome(
            imported=False,
            row_count=count(db),
            file_created_at=live.file_created_at,
            sha256=digest,
        )

    record = BankRegisterImport(
        filename=filename,
        sha256=digest,
        file_created_at=parsed.file_created_at,
        row_count=parsed.row_count,
        uploaded_by=staff_user_id,
    )
    db.add(record)
    db.flush()  # need the id to hang the branches off

    # A load is a REPLACE: the CB publishes a complete snapshot, so a branch that
    # has gone is gone. Safe here because the table is only read for prefill —
    # nothing references a branch row.
    db.execute(delete(BankBranch))
    db.add_all(
        [
            BankBranch(
                mfo=row.mfo,
                bank_name=row.bank_name,
                branch_name=row.branch_name or None,
                branch_type=row.branch_type or None,
                import_id=record.id,
            )
            for row in parsed.rows
        ]
    )
    db.flush()

    audit_service.write_audit(
        db,
        staff_user_id,
        "bank_register.import",
        "bank_register_imports",
        str(record.id),
        {
            "filename": filename,
            "rows": parsed.row_count,
            "sha256": digest,
            "file_created_at": (
                parsed.file_created_at.isoformat() if parsed.file_created_at else None
            ),
        },
    )

    return ImportOutcome(
        imported=True,
        row_count=parsed.row_count,
        file_created_at=parsed.file_created_at,
        sha256=digest,
    )
