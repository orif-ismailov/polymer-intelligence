"""Offer numbers are positive — the database says so too (audit IMEX-12).

The pentest stored `{"price": -500, "qty_available": -10}` through the portal PATCH:
the model's comment claimed positivity was "enforced in the API schema", which was
true of the webapp body and not of the portal one. Both schemas refuse it now; these
CHECKs are the layer no future schema can forget.

NULL stays legal everywhere — a made-to-order («под заказ») offer has no stock and
no price, and a free sample has no sample price.

Added `NOT VALID`: new and updated rows are checked from this moment, but existing
rows are not scanned, so a negative value already in production cannot fail the
deploy. Find and fix those, then `ALTER TABLE seller_offers VALIDATE CONSTRAINT …`.

Revision ID: 0057
Revises: 0056
"""

from __future__ import annotations

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_CHECKS = {
    "ck_offer_price_positive": "price IS NULL OR price > 0",
    "ck_offer_qty_positive": "qty_available IS NULL OR qty_available > 0",
    "ck_offer_min_order_positive": "min_order_qty IS NULL OR min_order_qty > 0",
    "ck_offer_sample_price_nonneg": "sample_price IS NULL OR sample_price >= 0",
}


def upgrade() -> None:
    for name, condition in _CHECKS.items():
        op.execute(f"ALTER TABLE seller_offers ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")


def downgrade() -> None:
    for name in _CHECKS:
        op.execute(f"ALTER TABLE seller_offers DROP CONSTRAINT IF EXISTS {name}")
