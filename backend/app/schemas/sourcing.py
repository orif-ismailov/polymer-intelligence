"""
Pydantic schemas for the AI broker dashboard (Phase 4): inventory, partner
suppliers, sourcing-run results, and the market-intelligence board.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import PriceBasis

# ── Inventory ───────────────────────────────────────────────────────────────────

class InventoryItemIn(BaseModel):
    product_id: int
    grade_text: str | None = Field(default=None, max_length=500)
    qty_on_hand: decimal.Decimal
    qty_unit: str = "MT"
    cost_price: decimal.Decimal | None = None
    currency: str = "USD"
    warehouse_city: str | None = Field(default=None, max_length=200)


class InventoryItemPatch(BaseModel):
    grade_text: str | None = None
    qty_on_hand: decimal.Decimal | None = None
    qty_unit: str | None = None
    cost_price: decimal.Decimal | None = None
    currency: str | None = None
    warehouse_city: str | None = None


class InventoryItemOut(BaseModel):
    id: int
    product_id: int
    grade_text: str | None
    qty_on_hand: decimal.Decimal
    qty_unit: str
    cost_price: decimal.Decimal | None
    currency: str
    warehouse_city: str | None
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Partner suppliers ────────────────────────────────────────────────────────────

class PartnerSupplierIn(BaseModel):
    name: str = Field(max_length=300)
    counterparty_id: int | None = None
    product_id: int | None = None
    grade_text: str | None = Field(default=None, max_length=500)
    indicative_price: decimal.Decimal | None = None
    currency: str = "USD"
    lead_time_days: int | None = None
    incoterms: PriceBasis = PriceBasis.unknown
    notes: str | None = Field(default=None, max_length=2000)


class PartnerSupplierPatch(BaseModel):
    name: str | None = None
    counterparty_id: int | None = None
    product_id: int | None = None
    grade_text: str | None = None
    indicative_price: decimal.Decimal | None = None
    currency: str | None = None
    lead_time_days: int | None = None
    incoterms: PriceBasis | None = None
    notes: str | None = None


class PartnerSupplierOut(BaseModel):
    id: int
    name: str
    counterparty_id: int | None
    product_id: int | None
    grade_text: str | None
    indicative_price: decimal.Decimal | None
    currency: str
    lead_time_days: int | None
    incoterms: PriceBasis
    notes: str | None
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Sourcing + intel (read-only result shapes) ───────────────────────────────────

class SourcingRunOut(BaseModel):
    id: int
    request_id: int
    model: str | None
    prompt_version: str | None
    result: dict[str, Any]
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class MarketIntelRow(BaseModel):
    code: str
    buyers: int
    sellers: int
    avg_seller_price: float | None
    avg_buyer_target: float | None
    spread: float | None
