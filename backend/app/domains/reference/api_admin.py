"""
Admin products router — manage the polymer product catalog (admin-only).

GET    /admin/products            — list all products (active + inactive)
POST   /admin/products            — add a product
PATCH  /admin/products/{id}       — edit / activate / deactivate a product

The active subset is served to the Telegram Web App selectors via
/webapp/reference/products, so adding a product here makes it appear in the app
without a client release. require_admin gates every route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.domains.reference import service as product_service
from app.domains.reference.schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/admin", tags=["admin-products"], dependencies=[Depends(require_admin)])


@router.get(
    "/products",
    response_model=list[ProductOut],
    summary="List all products (admin-only)",
)
def list_products(
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    """GET /admin/products — every product, active and inactive."""
    return product_service.list_all(db)  # type: ignore[return-value]


@router.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product (admin-only)",
)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
) -> ProductOut:
    """POST /admin/products — add a product. 409 if the code already exists."""
    try:
        product = product_service.create(db, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this code already exists",
        ) from None
    return product  # type: ignore[return-value]


@router.patch(
    "/products/{product_id}",
    response_model=ProductOut,
    summary="Update a product (admin-only)",
)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
) -> ProductOut:
    """PATCH /admin/products/{id} — partial update; 404 if not found."""
    product = product_service.get(db, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product_service.update(db, product, payload)  # type: ignore[return-value]
