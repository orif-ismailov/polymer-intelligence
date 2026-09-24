"""Portal reference data — the selectors on the add-product sheets.

The product catalog behind «Название товара». The Telegram Web App has had the
same list at `/webapp/reference/products` since the request wizard shipped, but
that route authenticates a Telegram `Client` — a portal account has no such
identity, so the cabinet needs its own door onto the same rows rather than a
widened guard on that one.

Requires a portal account but no company: the seller picks the product while
drafting, before the form knows which company is publishing (same reasoning as
`portal/substances.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.domains.reference import bank_service
from app.domains.reference import service as product_service
from app.domains.reference.schemas import BankBranchOut, ProductOut

router = APIRouter(prefix="/portal/reference", tags=["portal-reference"], dependencies=[Depends(get_current_account)])


@router.get(
    "/products",
    response_model=list[ProductOut],
    summary="Active polymer products for the offer selectors",
)
def list_products(
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    """GET /portal/reference/products — active products, ordered for the dropdown."""
    return product_service.list_active(db)  # type: ignore[return-value]


@router.get(
    "/banks/{mfo}",
    response_model=BankBranchOut,
    summary="The bank behind an MFO, for the registration bank step",
)
def bank_by_mfo(
    mfo: str = Path(min_length=5, max_length=5, pattern=r"^\d{5}$"),
    db: Session = Depends(get_db),
) -> BankBranchOut:
    """GET /portal/reference/banks/{mfo} — the bank name for a 5-digit MFO.

    A 404 is an ordinary answer here, not a problem: the register is a dated
    snapshot of the CB's list, and a branch it has not caught up with must still
    be registrable. The form says nothing and leaves the name free-typed.

    Unindexed by nothing and rate-limited by nothing on purpose: this is a single
    indexed read of a 324-row table behind an authenticated session, with no
    provider behind it to protect.
    """
    row = bank_service.bank_by_mfo(db, mfo)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bank_not_found")
    return row  # type: ignore[return-value]
