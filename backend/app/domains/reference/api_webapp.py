"""
/webapp/reference — public reference data for the Telegram Web App selectors.

Currently exposes the active product list (buyer + seller wizards). Authenticated
via initData like the rest of the webapp surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.domains.reference import service as product_service
from app.domains.reference.schemas import ProductOut
from app.domains.requests.models import Client

router = APIRouter(prefix="/webapp/reference", tags=["webapp-reference"])


@router.get(
    "/products",
    response_model=list[ProductOut],
    summary="Active polymer products for the request/offer selectors",
)
def list_products(
    db: Session = Depends(get_db),
    _client: Client = Depends(get_current_client),
) -> list[ProductOut]:
    """GET /webapp/reference/products — active products, ordered for the dropdowns."""
    return product_service.list_active(db)  # type: ignore[return-value]
