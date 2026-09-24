"""Load the shipped copy of the Central Bank's bank-branch register.

Without this a fresh deployment has an empty `bank_branches`, and the MFO prefill
on the registration bank step silently does nothing — which reads as a broken
field rather than as an unseeded table. The admin upload then refreshes it when
the CB republishes.

**Deliberately the same code path as the upload.** It calls
`bank_service.import_register`, so the parser, the validation and the
replace-in-one-transaction rule are exercised by both and tested once. A seeder
with its own loader would be a second implementation that drifts.

Idempotent by sha256: re-running on an unchanged file writes nothing and adds no
provenance row, so it is safe on every deploy.

Usage:
    python -m app.seed.seed_bank_register
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.domains.reference import bank_service

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent / "data" / "bank_branches.xlsx"


def seed_bank_register(db: Session | None = None, *, path: Path | None = None) -> str:
    """Seed/refresh the bank register. Commits when it owns the session.

    Returns a one-line summary for the seed runner's log.
    """
    own = db is None
    session = db or SessionLocal()
    source = path or _DATA_FILE
    try:
        if not source.exists():
            # Not fatal: a deployment can load the register from the admin panel.
            logger.warning("seed.bank_register.missing_file", extra={"path": str(source)})
            return "bank register file not found — skipped"

        outcome = bank_service.import_register(
            session, source.read_bytes(), source.name, staff_user_id=None
        )
        if own:
            session.commit()
        logger.info(
            "seed.bank_register",
            extra={"imported": outcome.imported, "rows": outcome.row_count},
        )
        if not outcome.imported:
            return f"already current — {outcome.row_count} branches"
        return f"loaded {outcome.row_count} branches (file dated {outcome.file_created_at})"
    finally:
        if own:
            session.close()


if __name__ == "__main__":
    print("Seeding bank register...")
    print(" ", seed_bank_register())
    print("Done.")
