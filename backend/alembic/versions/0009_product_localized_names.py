"""Localize product names: add products.name_en + products.name_tr.

The buyer/seller selectors and catalog chips render products in the app's four
locales (ru/en/uz/tr), but the products table only stored name_ru/name_uz — so
EN/TR users saw the Russian name. Add nullable name_en + name_tr and backfill the
eight seeded polymers so existing databases get localized names without a re-seed.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-29

IMPORTANT: Schema/data changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# code → (name_en, name_tr) for the eight seeded polymers (matches seed/data/products.json).
_BACKFILL: dict[str, tuple[str, str]] = {
    "PP": ("Polypropylene", "Polipropilen"),
    "HDPE": ("High-density polyethylene", "Yüksek yoğunluklu polietilen"),
    "LDPE": ("Low-density polyethylene", "Alçak yoğunluklu polietilen"),
    "LLDPE": ("Linear low-density polyethylene", "Doğrusal alçak yoğunluklu polietilen"),
    "PVC": ("Polyvinyl chloride", "Polivinil klorür"),
    "PET": ("Polyethylene terephthalate", "Polietilen tereftalat"),
    "PS": ("Polystyrene", "Polistiren"),
    "ABS": ("Acrylonitrile butadiene styrene", "Akrilonitril bütadien stiren"),
}


def upgrade() -> None:
    op.add_column("products", sa.Column("name_en", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("name_tr", sa.Text(), nullable=True))

    products = sa.table(
        "products",
        sa.column("code", sa.Text()),
        sa.column("name_en", sa.Text()),
        sa.column("name_tr", sa.Text()),
    )
    for code, (name_en, name_tr) in _BACKFILL.items():
        op.execute(
            products.update().where(products.c.code == code).values(name_en=name_en, name_tr=name_tr)
        )


def downgrade() -> None:
    op.drop_column("products", "name_tr")
    op.drop_column("products", "name_en")
