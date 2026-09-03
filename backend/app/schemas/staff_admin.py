"""
Staff administration schemas — the request/response contract for /admin/users.

These back the users screen an administrator uses to create colleagues and set
what each may reach. Access is expressed as a `{page: level}` map rather than a
list of rows: that is the shape the screen renders (one control per page) and
the shape a full replacement takes, so neither side has to diff anything.

`password_hash` appears in no model here, in either direction (T-04-13).
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.pages import PAGES, is_page

_MIN_PASSWORD_LENGTH = 12


def _validate_access(value: dict[str, str]) -> dict[str, str]:
    """Reject unknown pages and unknown levels.

    A grant nothing checks would grant nothing, and would read on the users
    screen as access the person does not have — so it is a 422, not a stored row.
    """
    for page, level in value.items():
        if not is_page(page):
            raise ValueError(f"Unknown page: {page!r}")
        if level not in ("read", "write"):
            raise ValueError(
                f"Unknown access level for {page!r}: {level!r} (expected 'read' or 'write')"
            )
    return value


class PageInfo(BaseModel):
    """One grantable page, for rendering the matrix.

    Carries no label — the dashboard already translates these keys into five
    languages under `nav.*`, and a second copy here would be the one that
    goes stale.
    """

    key: str
    group: str


class PageCatalogOut(BaseModel):
    """GET /admin/pages — every page that can be granted, in nav order."""

    pages: list[PageInfo]

    @classmethod
    def build(cls) -> PageCatalogOut:
        return cls(pages=[PageInfo(key=p.key, group=p.group) for p in PAGES])


class StaffUserListItem(BaseModel):
    """A row on the staff list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    granted_pages: int              # 0 for an administrator — they hold all of them implicitly
    created_at: datetime.datetime


class StaffUserDetail(BaseModel):
    """One staff account with its full access map."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    access: dict[str, str]
    created_at: datetime.datetime


class StaffUserCreate(BaseModel):
    """POST /admin/users.

    The password is set by the administrator and communicated out of band —
    there is no email infrastructure in this deployment, so an invite link is not
    available. It is hashed with argon2 before it touches the database.
    """

    email: str
    full_name: str
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH)
    is_admin: bool = False
    access: dict[str, str] = Field(default_factory=dict)

    @field_validator("access")
    @classmethod
    def _check_access(cls, v: dict[str, str]) -> dict[str, str]:
        return _validate_access(v)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        # The login lookup is case-sensitive, so an account created as
        # `Ivan@…` could never be signed into as `ivan@…`.
        return v.strip().lower()


class StaffUserPatch(BaseModel):
    """PATCH /admin/users/{id} — every field optional; omitted means unchanged.

    `email` is absent on purpose: it is the login identity and the audit trail's
    handle on a person. Renaming it silently re-points both.
    """

    full_name: str | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=_MIN_PASSWORD_LENGTH)


class StaffAccessUpdate(BaseModel):
    """PUT /admin/users/{id}/access — the complete access map, not a delta.

    Wholesale replacement, because the screen submits every page it rendered:
    a delta would leave a page the administrator un-ticked silently granted if
    the request lost it.
    """

    access: dict[str, str]

    @field_validator("access")
    @classmethod
    def _check_access(cls, v: dict[str, str]) -> dict[str, str]:
        return _validate_access(v)
