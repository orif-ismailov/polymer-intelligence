"""
Product reference service — CRUD over the `products` table.

Drives the dashboard admin product manager and the Telegram Web App selectors
(buyer/seller wizards). Products are no longer a hardcoded client-side list.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.reference.models import Product
from app.domains.reference.schemas import ProductCreate, ProductUpdate


def list_active(db: Session) -> list[Product]:
    """Active products for the public selectors, ordered by sort_order then id."""
    return list(
        db.scalars(
            select(Product).where(Product.is_active.is_(True)).order_by(Product.sort_order, Product.id)
        ).all()
    )


def list_all(db: Session) -> list[Product]:
    """All products (active + inactive) for the admin manager."""
    return list(db.scalars(select(Product).order_by(Product.sort_order, Product.id)).all())


def get(db: Session, product_id: int) -> Product | None:
    """Fetch a single product by id, or None."""
    return db.get(Product, product_id)


def create(db: Session, data: ProductCreate) -> Product:
    """Insert a new product. Raises IntegrityError on a duplicate `code`."""
    product = Product(
        code=data.code.strip(),
        name_ru=data.name_ru.strip(),
        name_uz=data.name_uz.strip() if data.name_uz else None,
        name_en=data.name_en.strip() if data.name_en else None,
        name_tr=data.name_tr.strip() if data.name_tr else None,
        category=data.category,
        sort_order=data.sort_order,
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update(db: Session, product: Product, data: ProductUpdate) -> Product:
    """Apply a partial update (only provided fields) and persist."""
    if data.name_ru is not None:
        product.name_ru = data.name_ru.strip()
    if data.name_uz is not None:
        product.name_uz = data.name_uz.strip() or None
    if data.name_en is not None:
        product.name_en = data.name_en.strip() or None
    if data.name_tr is not None:
        product.name_tr = data.name_tr.strip() or None
    if data.category is not None:
        product.category = data.category
    if data.sort_order is not None:
        product.sort_order = data.sort_order
    if data.is_active is not None:
        product.is_active = data.is_active
    db.commit()
    db.refresh(product)
    return product
