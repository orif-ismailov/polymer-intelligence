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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.core.db import get_db
from app.domains.accounts.models import UserAccount
from app.domains.reference import service as product_service
from app.domains.reference.schemas import ProductOut

router = APIRouter(prefix="/portal/reference", tags=["portal-reference"])


@router.get(
    "/products",
    response_model=list[ProductOut],
    summary="Active polymer products for the offer selectors",
)
def list_products(
    db: Session = Depends(get_db),
    _account: UserAccount = Depends(get_current_account),
) -> list[ProductOut]:
    """GET /portal/reference/products — active products, ordered for the dropdown."""
    return product_service.list_active(db)  # type: ignore[return-value]
