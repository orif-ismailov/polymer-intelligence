"""
Pydantic schemas for reference data (products) — managed via the dashboard admin
and consumed by the Telegram Web App's product selectors.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    """A polymer product as returned to the webapp selectors and the admin list."""

    id: int
    code: str
    name_ru: str
    name_uz: str | None = None
    category: str
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    """Admin payload to add a new product to the catalog."""

    code: str = Field(min_length=1, max_length=50)
    name_ru: str = Field(min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    category: str = Field(default="polymer", min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    """Admin payload to edit / activate / deactivate a product. All fields optional."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
