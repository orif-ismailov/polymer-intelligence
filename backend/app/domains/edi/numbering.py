"""Document numbers for the Didox rail (P7.a Stage 2 — W6).

Two rules, both learned from how these numbers are actually used:

  * **An ЭСФ number is per SELLER COMPANY, per year.** It has to be unique in that
    seller's own books; a global counter would leave gaps in every seller's
    numbering that their accountant will ask about. Sequence
    `esf_seq_{company_id}_{year}`, created lazily on that seller's first invoice.
  * **A contract number is allocated once and then quoted, never recomputed.** The
    ЭСФ carries `ContractDoc.ContractNo`, and the roaming centre refuses a pair
    whose numbers disagree — so the ЭСФ reads it off the stored 007 row rather
    than deriving it again from the deal.

Both are written to `didox_documents.number` BEFORE the create call, so a retried
create reuses the number instead of burning a second one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.numbering import LOCK_BASE_ESF, next_in_sequence

if TYPE_CHECKING:  # pragma: no cover
    import datetime

    from sqlalchemy.orm import Session


def next_facture_number(db: Session, seller_company_id: int, on: datetime.date) -> str:
    """`ЭСФ-{year}-{NNNNNN}` from the seller's own yearly sequence."""
    sequence = f"esf_seq_{seller_company_id}_{on.year}"
    value = next_in_sequence(db, sequence, LOCK_BASE_ESF + on.year)
    return f"ЭСФ-{on.year}-{value:06d}"


def contract_number(*, deal_number: str | None, contract_public_id: str) -> str:
    """The договор's number.

    Prefers the deal's own number (`DEAL-2026-000125`) because the humans on both
    sides already use it everywhere — chat, documents, the escrow row — and a
    second identifier for the same transaction is a support ticket waiting to
    happen. Falls back to the contract's public id for a contract with no deal.
    """
    if deal_number:
        return deal_number
    return f"C-{contract_public_id[:8]}"
