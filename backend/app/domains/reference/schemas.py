"""
Pydantic schemas for reference data — products (managed via the dashboard admin and
consumed by the Telegram Web App's product selectors) and the Central Bank's bank
register (loaded whole, read by MFO).
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    """A polymer product as returned to the webapp selectors and the admin list."""

    id: int
    code: str
    name_ru: str
    name_uz: str | None = None
    name_en: str | None = None
    name_tr: str | None = None
    category: str
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    """Admin payload to add a new product to the catalog."""

    code: str = Field(min_length=1, max_length=50)
    name_ru: str = Field(min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    name_tr: str | None = Field(default=None, max_length=200)
    category: str = Field(default="polymer", min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    """Admin payload to edit / activate / deactivate a product. All fields optional."""

    name_ru: str | None = Field(default=None, min_length=1, max_length=200)
    name_uz: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    name_tr: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


# ── bank register ─────────────────────────────────────────────────────────────


class BankBranchOut(BaseModel):
    """One branch, as the registration form reads it.

    Deliberately narrow: the form fills a bank NAME, and the branch name is only
    there so an operator can tell whether the MFO they typed is the office they
    meant. The register's other columns (address, region, STIR, website) are not
    served because nothing asks for them.
    """

    mfo: str
    bank_name: str
    branch_name: str | None = None

    model_config = {"from_attributes": True}


class BankRegisterStatusOut(BaseModel):
    """What the admin screen shows about the live register.

    `file_created_at` is the register's OWN publication date and is the field that
    answers "is our copy stale?" — `uploaded_at` only says when we noticed.
    `uploaded_by` is None for the copy that shipped with the release.
    """

    loaded: bool
    row_count: int
    filename: str | None = None
    file_created_at: datetime.date | None = None
    uploaded_at: datetime.datetime | None = None
    uploaded_by: str | None = None


class BankRegisterImportOut(BaseModel):
    """The result of one upload. `imported=False` means the same file was already
    live and nothing changed — an answer, not an error."""

    imported: bool
    row_count: int
    file_created_at: datetime.date | None = None
